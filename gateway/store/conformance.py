"""The contract, `conformance(backend)`, run against BOTH backends: here in the gate against
MemoryBackend, and by scripts/rls_integration.py against PostgresBackend on a real server."""
from __future__ import annotations

from gateway.store.core import (CASCADE_KEYS, DECISION_KEYS, DRAFT_VERSION_KEYS,
    DecisionExists, DuplicateVaultDocument, GRID_CELL_KEYS, MESSAGE_KEYS, MessageShape,
    PROPOSITION_KEYS, STEP_KEYS, StoreError, TurnConflict, step_key)


# ── the contract, run against BOTH backends ──────────────────────────────────

SAMPLE_RUN = {
    "id": "00000000-0000-0000-0000-0000000000r1".replace("r", "9"),
    "intent": "review_contract",
    "status": "ANSWERED",
    "refusal_code": None,
    "steps": [
        {"capability": "intake", "engine_capability": None, "status": "ANSWERED",
         "model": None, "degraded": False},
        {"capability": "document", "engine_capability": "document.ground_extraction",
         "status": "ANSWERED", "model": "azure/llama-3-3-70b", "degraded": True,
         "provider": "azure", "region": "UAE North", "cost_inr": None,
         "cost_note": "UNPRICED: no verified price on record for this deployment"},
        {"capability": "playbook", "engine_capability": "contract.playbook_review",
         "status": "ANSWERED", "model": None, "degraded": False},
    ],
    "propositions": [
        {"status": "VERIFIED", "source_ref": "contract:nda", "span_start": 10,
         "span_end": 42},
        {"status": "UNVERIFIED", "source_ref": None, "span_start": None,
         "span_end": None},
    ],
}


def conformance(backend) -> list[tuple[bool, str]]:
    """Every assertion both backends must satisfy. No I/O beyond the backend itself.

    Called by this module's gated test with MemoryBackend, and by
    scripts/rls_integration.py with PostgresBackend against a live server. One list, two
    callers -- a behaviour only the dict satisfies fails identically on Postgres.
    """
    out: list[tuple[bool, str]] = []

    def ck(cond, label):
        out.append((bool(cond), label))

    import uuid as _uuid
    # A FRESH id per call. SAMPLE_RUN carried a fixed one, and against a shared Postgres
    # that means two tenants writing the same run id: the second one's ON CONFLICT DO
    # UPDATE reaches a row belonging to the first, and row-level security refuses it --
    # correctly. Measured 29-09-2026. The isolation was right and the fixture was wrong.
    run = dict(SAMPLE_RUN, id=str(_uuid.uuid4()))

    ck(backend.read_run("no-such-run") is None,
       "an unknown run reads as None, not as an empty run")
    ck(backend.read_run(str(_uuid.uuid4())) is None,
       "...and a well-formed id that names no run reads as None too")

    backend.write_run(run)
    got = backend.read_run(run["id"])
    ck(got is not None, "a written run reads back")
    if got:
        ck(got["status"] == "ANSWERED" and got["intent"] == "review_contract",
           "...with its intent and status")
        ck([s["capability"] for s in got["steps"]]
           == ["intake", "document", "playbook"],
           "...and its steps IN ORDER, which is what makes a trace replayable")
        ck(got["steps"][1]["model"] == "azure/llama-3-3-70b"
           and got["steps"][1]["degraded"] is True,
           "...carrying which model served a step and whether the route was degraded")
        ck(got["steps"][1]["provider"] == "azure"
           and got["steps"][1]["region"] == "UAE North",
           "...and the provider and the deployment REGION, so a trace answers 'where did "
           "this document go' without reading a deployment note")
        ck(got["steps"][1]["cost_inr"] is None
           and "UNPRICED" in (got["steps"][1]["cost_note"] or ""),
           "...and an unpriced call records NULL with its reason, never 0.0: Azure bills "
           "student credit, so a recorded zero would be a claim the call was free")
        ck([p["status"] for p in got["propositions"]] == ["VERIFIED", "UNVERIFIED"],
           "...and its propositions, in order")
        ck(got["propositions"][0]["span_start"] == 10
           and got["propositions"][0]["span_end"] == 42,
           "...with span OFFSETS, not copied text")

    # Idempotence: writing the same run twice is one run with one set of steps.
    backend.write_run(run)
    again = backend.read_run(run["id"])
    ck(again and len(again["steps"]) == 3,
       "re-writing a run replaces its steps rather than appending them again")

    # The caller's dict is not the store's dict.
    mutant = dict(run)
    mutant["steps"] = [dict(s) for s in run["steps"]]
    backend.write_run(mutant)
    mutant["steps"][0]["capability"] = "TAMPERED"
    after = backend.read_run(run["id"])
    ck(after and after["steps"][0]["capability"] == "intake",
       "mutating the dict AFTER writing does not change the store -- a backend that kept "
       "the caller's object would pass tests a database cannot")

    # A step written WITHOUT its optional keys must read back WITH them. Postgres returns
    # every column; a dict returns what it was handed, and `step["model"]` would then be a
    # KeyError on memory and None on Postgres. Caught the hard way on 29-09-2026, when the
    # CLI demo raised KeyError('model') on a step the sample run happened to populate.
    sparse_id = str(_uuid.uuid4())
    backend.write_run({"id": sparse_id, "intent": "ask", "status": "ANSWERED",
                       "steps": [{"capability": "intake", "status": "ANSWERED"}],
                       "propositions": [{"status": "VERIFIED"}]})
    sp = backend.read_run(sparse_id)
    ck(sp and set(sp["steps"][0]) == set(STEP_KEYS),
       f"a step written with two keys reads back with all of them "
       f"({sorted(sp['steps'][0]) if sp else []})")
    ck(sp and sp["steps"][0]["model"] is None and sp["steps"][0]["degraded"] is False,
       "...the absent ones defaulted, not missing -- so step['model'] is never a KeyError "
       "on one backend and None on the other")
    ck(sp and set(sp["propositions"][0]) == set(PROPOSITION_KEYS),
       "...and the same for a proposition")
    ck(sp and "law_versions" in sp and sp["law_versions"] is None,
       "a run written with no law versions reads back with None -- not recorded, which is "
       "not the same claim as 'read no law'")

    # The law versions a run read (PLAN_23 layer 10), stored by value.
    lv = {"corpus/reference/SS-1.txt": "a" * 40, "playbooks/nda_v1.json": "b" * 40}
    lv_id = str(_uuid.uuid4())
    lv_run = {"id": lv_id, "intent": "review_document", "status": "ANSWERED",
              "steps": [], "propositions": [], "law_versions": lv}
    backend.write_run(lv_run)
    lv["corpus/reference/SS-1.txt"] = "TAMPERED"
    ck((backend.read_run(lv_id) or {}).get("law_versions")
       == {"corpus/reference/SS-1.txt": "a" * 40, "playbooks/nda_v1.json": "b" * 40},
       "a run's law versions read back as written, and a later change to the caller's map "
       "does not reach the store")

    # A null cost always says WHY it is null.
    nulls = [st for st in (backend.read_run(sparse_id) or {}).get("steps", [])
             if st["cost_inr"] is None]
    ck(nulls and all(st["cost_note"] for st in nulls),
       "every step with a null cost carries a reason -- a blank beside a null is "
       "indistinguishable from a cost nobody bothered to record")

    ck(backend.get_document("0" * 64) is None, "an unknown document reads as None")
    sha = _uuid.uuid4().hex + _uuid.uuid4().hex
    doc = backend.put_document(sha256=sha, name="nda.txt", byte_count=33)
    ck(doc["sha256"] == sha, "a document is stored under its sha256")
    back = backend.get_document(sha)
    ck(back and back["byte_count"] == 33 and back["name"] == "nda.txt",
       "...and reads back with its name and size")
    backend.put_document(sha256=sha, name="nda.txt", byte_count=33)
    ck(backend.get_document(sha) is not None,
       "storing the same bytes twice is not an error: the id IS the hash, so it is one "
       "document")

    # ── the human gate, stored as labelled data (PLAN_23 rule 5) ────────────
    ck(backend.read_decisions(run["id"]) == [],
       "a run with no human decision reads as an empty list, not as a missing key")
    dec = {"decision_id": str(_uuid.uuid4()), "run_id": run["id"],
           "item_ref": "playbook:NDA-08", "decision": "REJECTED",
           "reason": "The non-compete is one-way and we do not accept those.",
           "quoted_span": "The Receiving Party shall not compete for two years.",
           "quote_viewed": False,
           "law_versions": {"playbooks/nda_v1.json": "c" * 40},
           "actor_id": "00000000-0000-0000-0000-0000000000a1",
           "decided_at": "2026-09-30T10:00:00+00:00"}
    wrote = backend.write_decision(dict(dec))
    ck(set(wrote) == set(DECISION_KEYS),
       f"a decision reads back with every key both backends promise ({sorted(wrote)})")
    got = backend.read_decisions(run["id"])
    ck(len(got) == 1 and got[0]["reason"] == dec["reason"],
       "...and the reason is stored verbatim: it IS the label")
    ck(got[0]["quoted_span"] == dec["quoted_span"],
       "...with the span the reviewer was shown, so the label is attached to text a person "
       "actually read")
    ck(got[0]["decided_at"],
       "...and a time, defaulted by the store when the caller gives none")
    ck(got[0]["quote_viewed"] is False
       and got[0]["law_versions"] == {"playbooks/nda_v1.json": "c" * 40},
       "...and whether the quote was viewed, and the law versions it was decided against")

    # One per item, on BOTH backends. Without this the dict keeps two labels for one item
    # and Postgres keeps one, and the disagreement surfaces as a lost review months later.
    try:
        backend.write_decision(dict(dec, decision_id=str(_uuid.uuid4()),
                                    decision="APPROVED", quote_viewed=True,
                                    reason="Changed my mind about it."))
        ck(False, "a second decision on the same item is refused")
    except DecisionExists:
        ck(True, "a second decision on the SAME item is refused -- overwriting would "
                 "destroy the label, which is the point of storing it")
    ck(len(backend.read_decisions(run["id"])) == 1,
       "...and nothing was written by the attempt")

    # A different item on the same run is a different label.
    backend.write_decision(dict(dec, decision_id=str(_uuid.uuid4()),
                                item_ref="ss:T1.2", decision="APPROVED",
                                quote_viewed=True,
                                reason="Inspected the book; every page is initialled."))
    ck(len(backend.read_decisions(run["id"])) == 2,
       "...while a different item on the same run is a separate decision")

    # ── idempotent steps: a retried step writes once (PLAN_23 O2) ───────────
    idem = str(_uuid.uuid4())
    backend.write_run({"id": idem, "intent": "review_document", "status": "PLANNED",
                       "steps": [], "propositions": []})
    k = step_key(idem, "document")
    step = {"capability": "document", "status": "ANSWERED", "provider": "azure",
            "region": "UAE North", "cost_inr": 0.05, "cost_note": "priced from tokens"}
    ck(backend.append_step(idem, step, key=k) is True,
       "a step appends and says it was written")
    ck(backend.append_step(idem, step, key=k) is False,
       "...and the SAME key appends nothing and says so -- which is how a worker tells a "
       "resumed run from a fresh one")
    after = backend.read_run(idem)
    ck(after and len(after["steps"]) == 1,
       f"...so a retried step is written ONCE ({len(after['steps']) if after else '?'})")
    total = sum(s["cost_inr"] or 0 for s in after["steps"])
    ck(abs(total - 0.05) < 1e-9,
       f"...and billed once: the cost rides on the step row, so a duplicate step IS a "
       f"duplicate charge ({total})")
    ck(after["steps"][0]["idempotency_key"] == k,
       "...and the key is readable, so the record says why the second write did nothing")
    ck(backend.append_step(idem, {**step, "capability": "playbook"},
                           key=step_key(idem, "playbook")) is True,
       "...while a DIFFERENT step on the same run still appends")

    # ── the run's status and result move without rewriting its steps ────────
    backend.set_run(idem, status="ANSWERED", result={"findings": 3})
    done = backend.read_run(idem)
    ck(done["status"] == "ANSWERED" and len(done["steps"]) == 2,
       f"setting the status leaves the trace alone ({done['status']}, "
       f"{len(done['steps'])} steps)")
    ck(done.get("result") == {"findings": 3},
       f"...and the result is readable by a poller once the status goes final "
       f"({done.get('result')})")
    # ── cascade records (PLAN_23 O3) ───────────────────────────────────────
    ck(backend.read_cascades(run_id=idem) == [],
       "a run with no cascade record reads as an empty list")
    cid = str(_uuid.uuid4())
    casc = {"cascade_id": cid, "status": "PARTIAL", "error": None,
            "attempts": [{"stage": "small_model", "outcome": "REJECTED",
                          "reason": "NO_CITATION: invented", "model": "s",
                          "cost_inr": 0.02, "cost_note": ""},
                         {"stage": "large_model", "outcome": "ACCEPTED", "reason": "",
                          "model": "l", "cost_inr": 0.10, "cost_note": ""}],
            "body_ids": ["CA2013", "FEMA1999"],
            "claims": [{"text": "t"}], "refusals": [{"body": "FEMA1999"}],
            "total_cost_inr": 0.12}
    wrote = backend.write_cascade(dict(casc), run_id=idem)
    ck(set(wrote) == set(CASCADE_KEYS),
       f"a cascade record reads back with every key both backends promise "
       f"({sorted(wrote)})")
    got_c = backend.read_cascades(run_id=idem)
    ck(len(got_c) == 1 and got_c[0]["status"] == "PARTIAL",
       "...and is findable by the run it belonged to")
    ck([a["stage"] for a in got_c[0]["attempts"]] == ["small_model", "large_model"],
       f"...with its attempts IN ORDER: stage 2 only ran because stage 1 was rejected, "
       f"and a record that must be re-sorted to see that has lost it "
       f"({[a['stage'] for a in got_c[0]['attempts']]})")
    ck(got_c[0]["attempts"][0]["reason"] == "NO_CITATION: invented",
       "...each carrying the verifier's rejection reason, which is what a rate counts")
    ck(got_c[0]["body_ids"] == ["CA2013", "FEMA1999"],
       f"...and every body the answer touched ({got_c[0]['body_ids']})")
    ck(abs((got_c[0]["total_cost_inr"] or 0) - 0.12) < 1e-9,
       "...and the total cost, including the rejected stage")

    unp = backend.write_cascade({"status": "NEEDS_LAWYER", "attempts": [],
                                 "body_ids": [], "total_cost_inr": None}, run_id=idem)
    ck(unp["total_cost_inr"] is None,
       "an unpriced cascade stores NULL, which is UNPRICED")
    for bad, why in (
        ({"status": "FAILED", "attempts": [], "body_ids": []},
         "FAILED with no error"),
        ({"status": "ANSWERED", "error": "boom", "attempts": [], "body_ids": []},
         "a non-FAILED record carrying a transport error"),
        ({"status": "ANSWERED", "attempts": [], "body_ids": [], "total_cost_inr": 0},
         "a recorded cost of 0, which would claim the calls were free"),
        ({"status": "MAYBE", "attempts": [], "body_ids": []}, "an unknown status"),
    ):
        try:
            backend.write_cascade(dict(bad), run_id=idem)
            ck(False, f"{why} is refused")
        except StoreError:
            ck(True, f"refused: {why}")
    ck(len(backend.read_cascades(run_id=idem)) == 2,
       "...and none of the refused records was written")
    ck(len(backend.read_cascades()) >= 2,
       "cascades are readable without naming a run, which is what the report needs")

    backend.set_run(idem, status="REFUSED", refusal_code="CANCELLED")
    ck(backend.read_run(idem)["refusal_code"] == "CANCELLED",
       "...and a cancelled run keeps its code, which is what the trace is read for")
    ck(len(backend.read_run(idem)["steps"]) == 2,
       "...with every step it had: cancellation never deletes")

    # ── C2: the chat layer, on BOTH backends ────────────────────────────────
    # These run against MemoryBackend in the gate and against PostgresBackend in
    # scripts/rls_integration.py, so a behaviour only the dict satisfies fails identically
    # on Postgres. The row-shape refusals below are 010's own CHECKs, restated in code so
    # the two backends refuse the same rows rather than one of them accepting it.
    import uuid as _uuid
    cid = str(_uuid.uuid4())
    # 8b: a conversation is filed to a matter, and the listing is scoped to one.
    _CONF_MATTER = str(_uuid.uuid4())
    # 028: the conformance actor files work to a matter it owns, as matters.create grants.
    backend.write_matter({"matter_id": _CONF_MATTER, "name": f"conformance {_CONF_MATTER[:8]}"},
                         owner=getattr(backend, "_session_actor", None) or None)
    backend.write_conversation({"conversation_id": cid, "title": "board meeting",
                                "matter_id": _CONF_MATTER})
    conv = backend.read_conversation(cid)
    ck(conv is not None and conv["title"] == "board meeting",
       "a conversation is written and read back")
    ck(backend.read_conversation(str(_uuid.uuid4())) is None,
       "...and an unknown conversation reads as None, not an empty one")
    ck(any(c["conversation_id"] == cid
           for c in backend.list_conversations(matter_id=_CONF_MATTER)),
       "...and appears in the list")

    m0, m1 = str(_uuid.uuid4()), str(_uuid.uuid4())
    backend.append_message({"message_id": m0, "conversation_id": cid, "ordinal": 0,
                            "role": "user", "text": "are we late on MGT-7?",
                            "file_ids": ["abc"]})
    backend.append_message({"message_id": m1, "conversation_id": cid, "ordinal": 1,
                            "role": "assistant", "text": "", "file_ids": [],
                            "task": "RESEARCH_QUESTION"})
    thread = backend.read_messages(cid)
    ck([m["ordinal"] for m in thread] == [0, 1], "messages read back IN ORDER")
    ck([m["role"] for m in thread] == ["user", "assistant"], "...with their roles")
    ck(thread[0]["file_ids"] == ["abc"], "...and the user message keeps its file_ids")
    ck(all(set(m) >= set(MESSAGE_KEYS) for m in thread),
       f"...and every message has every key on both backends ({sorted(thread[0])})")
    ck(thread[1]["envelope"] is None,
       "an assistant message with no reply yet has envelope None -- NOT {}, which would "
       "claim an empty answer")

    ck(backend.set_message_envelope(m1, {"schema": "answer_envelope.v1",
                                         "status": "ANSWERED"}),
       "the envelope is written when the reply arrives")
    ck(backend.read_messages(cid)[1]["envelope"]["status"] == "ANSWERED",
       "...and reads back as an object")
    ck(not backend.set_message_envelope(str(_uuid.uuid4()), {"schema": "x"}),
       "...and an unknown message id is False, not a silent no-op")
    # A USER message may not gain an envelope. The dict RAISES; Postgres returns False,
    # because it enforces it with `AND role = 'assistant'` in the UPDATE. Both are
    # refusals and neither writes, so the assertion is on the OUTCOME -- the message still
    # has no envelope -- rather than on which mechanism said no.
    try:
        wrote = backend.set_message_envelope(m0, {"schema": "x"})
    except (StoreError, MessageShape):
        wrote = False
    ck(not wrote, "a USER message cannot be given an envelope")
    ck(backend.read_messages(cid)[0]["envelope"] is None,
       "...and it still has none afterwards, whichever way it was refused")

    for bad, why in (
        ({"message_id": str(_uuid.uuid4()), "conversation_id": cid, "ordinal": 2,
          "role": "system", "text": "you are a helpful assistant"},
         "role 'system' -- a system prompt belongs to the run, not the conversation"),
        ({"message_id": str(_uuid.uuid4()), "conversation_id": cid, "ordinal": 2,
          "role": "user", "text": "x", "envelope": {"schema": "x"}},
         "a user message carrying an envelope"),
        ({"message_id": str(_uuid.uuid4()), "conversation_id": cid, "ordinal": 2,
          "role": "assistant", "text": "x", "file_ids": ["f"]},
         "an assistant message carrying file_ids"),
        ({"message_id": str(_uuid.uuid4()), "conversation_id": cid, "ordinal": -1,
          "role": "user", "text": "x"}, "a negative ordinal"),
        ({"message_id": str(_uuid.uuid4()), "conversation_id": cid, "ordinal": 0,
          "role": "user", "text": "x"}, "an ordinal already used in this conversation"),
    ):
        try:
            backend.append_message(dict(bad))
            ck(False, f"{why} is refused")
        except StoreError:
            ck(True, f"refused: {why}")
    ck(len(backend.read_messages(cid)) == 2,
       "...and none of the refused messages was written")
    try:
        backend.append_message({"message_id": str(_uuid.uuid4()),
                                "conversation_id": str(_uuid.uuid4()), "ordinal": 0,
                                "role": "user", "text": "x"})
        ck(False, "a message for a conversation that does not exist is refused")
    except Exception:
        ck(True, "a message for a conversation that does not exist is refused")

    # A single reservation owns both ordinal slots and the stable retry ID.
    rid = str(_uuid.uuid4())
    reply_id = str(_uuid.uuid4())
    metadata = {"schema": "conversation_turn.v1", "request_id": rid,
                "artifacts": [{"type": "draft", "id": str(_uuid.uuid4()), "version": 1}]}
    reserve_args = ({"conversation_id": cid, "matter_id": _CONF_MATTER},
                    {"message_id": str(_uuid.uuid4()), "role": "user", "text": "next"},
                    {"message_id": reply_id, "role": "assistant", "text": "",
                     "metadata": metadata})
    reserved, created = backend.reserve_turn(*reserve_args, request_id=rid, payload_digest="a" * 64)
    ck(created and reserved["ordinal"] == 3, "reservation allocates an adjacent pair atomically")
    repeated, created_again = backend.reserve_turn(*reserve_args, request_id=rid, payload_digest="a" * 64)
    ck(not created_again and repeated["message_id"] == reply_id,
       "repeated request returns its original reply without appending messages")
    ck(len(backend.read_messages(cid)) == 4, "the duplicate did not allocate another ordinal")
    try:
        backend.find_turn(rid, "b" * 64)
        ck(False, "changed payload with the same request ID conflicts")
    except TurnConflict:
        ck(True, "changed payload with the same request ID conflicts")
    ck(backend.update_message(reply_id, task="DRAFT", run_id=None,
                              envelope={"status": "PARTIAL"}, metadata=metadata),
       "turn completion persists the envelope and sibling metadata together")
    reopened = backend.read_messages(cid)[3]
    ck(reopened["metadata"] == metadata and reopened["envelope"]["status"] == "PARTIAL",
       "artifact metadata and honest outcome survive a reload")

    # ── H4: review grids, on BOTH backends ──────────────────────────────────
    gid = str(_uuid.uuid4())
    DOC_A, DOC_B = "a" * 64, "b" * 64
    backend.write_grid({"grid_id": gid, "name": "NDA diligence",
                        "columns": [{"name": "governing law", "kind": "text",
                                     "question": "Which law governs?"},
                                    {"name": "term end", "kind": "date",
                                     "question": "When does it expire?"}],
                        "document_ids": [DOC_A, DOC_B]})
    g = backend.read_grid(gid)
    ck(g is not None and g["name"] == "NDA diligence", "a grid is written and read back")
    ck([c["name"] for c in g["columns"]] == ["governing law", "term end"],
       "...with its columns IN ORDER, which is the order the CSV exports")
    ck(sorted(g["document_ids"]) == sorted([DOC_A, DOC_B]), "...and its documents")
    ck(backend.read_grid(str(_uuid.uuid4())) is None,
       "...and an unknown grid reads as None, not an empty one")
    ck(g["document_names"] == {}, "034: a grid written with no file names reads {}")
    gid_n = str(_uuid.uuid4())
    backend.write_grid({"grid_id": gid_n, "name": "Named",
                        "columns": [{"name": "c", "kind": "text", "question": "Which?"}],
                        "document_ids": [DOC_A, DOC_B],
                        "document_names": {DOC_A: "nda.pdf", DOC_B: "lease.docx"}})
    ck(backend.read_grid(gid_n)["document_names"] == {DOC_A: "nda.pdf", DOC_B: "lease.docx"},
       "034: ...and one written with file names reads them back, on both backends")
    # review_table.list: the firm's tables, newest first, counts and no contents.
    listed = [r for r in backend.list_grids(limit=51) if r["grid_id"] == gid]
    ck(len(listed) == 1 and listed[0]["name"] == "NDA diligence"
       and (listed[0]["columns"], listed[0]["documents"], listed[0]["cells"],
            listed[0]["pending"]) == (2, 2, 4, 4)
       and listed[0]["created_at"] and listed[0]["cancelled_at"] is None,
       "list_grids names the grid with its column, document, cell and pending counts")
    ck(set(listed[0] if listed else ()) == {
           "grid_id", "name", "created_at", "cancelled_at", "paused_budget", "actor_id",
           "matter_id", "columns", "documents", "cells", "pending"},
       "...and carries no question text and no cell value, on either backend")
    gid2 = str(_uuid.uuid4())
    backend.write_grid({"grid_id": gid2, "name": "Lease review",
                        "columns": [{"name": "rent", "kind": "amount",
                                     "question": "What is the monthly rent?"}],
                        "document_ids": [DOC_A]})
    order = [r["grid_id"] for r in backend.list_grids(limit=51)
             if r["grid_id"] in (gid, gid2)]
    ck(order == [gid2, gid], "...newest first")
    first = backend.list_grids(limit=1)
    ck(len(first) == 1 and first[0]["grid_id"] == gid2, "...and a page stops at its limit")
    after = backend.list_grids(limit=51, before_created_at=first[0]["created_at"],
                               before_grid_id=gid2)
    ck(gid2 not in {r["grid_id"] for r in after} and gid in {r["grid_id"] for r in after},
       "...and the cursor continues strictly after the last row it returned")
    for bad in ({"limit": 0}, {"limit": 52},
                {"limit": 5, "before_created_at": "2026-01-01T00:00:00+00:00"},
                {"limit": 5, "before_created_at": "2026-01-01T00:00:00+00:00",
                 "before_grid_id": "nope"}):
        try:
            backend.list_grids(**bad)
            ck(False, f"list_grids refuses {bad}")
        except StoreError:
            ck(True, f"list_grids refuses {bad} on both backends alike")
    cells = backend.read_grid_cells(gid)
    ck(len(cells) == 4 and {c["state"] for c in cells} == {"PENDING"},
       f"creating a grid materialises every cell as PENDING ({len(cells)}) -- a missing "
       f"row and a PENDING one must not be the same thing")
    ck(all(set(c) >= set(GRID_CELL_KEYS) for c in cells),
       f"...and every cell has every key on both backends ({sorted(cells[0])})")
    ck(all(c["cost_inr"] is None for c in cells),
       "...and a PENDING cell has NO cost: nothing has happened to it, and 0.00 would say "
       "the call was free")
    ck(all("not a cost of zero" in (c["cost_note"] or "") for c in cells),
       f"...and its note SAYS that null is not zero, identically on both backends -- the "
       f"dict normalised a null cost's note and Postgres returned NULL until the "
       f"conformance list ran these columns ({(cells[0]['cost_note'] or '')[:40]!r})")

    ok1 = backend.write_grid_cell({"grid_id": gid, "document_id": DOC_A,
                                   "column_name": "governing law", "state": "FOUND",
                                   "value": "India",
                                   "quote": "governed by the laws of India",
                                   "provider": "azure", "cost_inr": 0.0412,
                                   "cost_note": "one extraction call, priced from the "
                                                "tokens the provider reported"})
    ck(ok1, "a PENDING cell is answered")
    got = {(c["document_id"], c["column_name"]): c
           for c in backend.read_grid_cells(gid)}
    ck(got[(DOC_A, "governing law")]["state"] == "FOUND"
       and got[(DOC_A, "governing law")]["quote"].endswith("India"),
       "...and reads back with its value and quote")
    _priced = got[(DOC_A, "governing law")]
    ck(_priced["cost_inr"] == 0.0412 and _priced["provider"] == "azure",
       f"...and with its DEBIT: the rupees and the provider round-trip through both "
       f"backends ({_priced['cost_inr']!r} / {_priced['provider']!r})")
    ck(isinstance(_priced["cost_inr"], float),
       f"...as a float on both, not Decimal on one -- a caller summing a grid's cells "
       f"would hit a TypeError on exactly one backend ({type(_priced['cost_inr']).__name__})")
    ck(backend.write_grid_cell({"grid_id": gid, "document_id": DOC_B,
                               "column_name": "governing law", "state": "NOT_FOUND",
                               "reason": "the document was read and does not answer it",
                               "provider": "azure", "cost_inr": None,
                               "cost_note": "UNPRICED: no verified price is held for this "
                                            "deployment"}),
       "a cell whose call cannot be priced writes UNPRICED -- NULL with a note -- and is "
       "accepted, because the alternative on offer is a zero that means free")
    _unp = {(c["document_id"], c["column_name"]): c
            for c in backend.read_grid_cells(gid)}[(DOC_B, "governing law")]
    ck(_unp["cost_inr"] is None and _unp["cost_note"].startswith("UNPRICED"),
       f"...and reads back still UNPRICED, never coerced to 0 ({_unp['cost_inr']!r})")

    # The exactly-once half that lives in code: a terminal cell is not overwritten.
    again = backend.write_grid_cell({"grid_id": gid, "document_id": DOC_A,
                                     "column_name": "governing law", "state": "NOT_FOUND",
                                     "reason": "a resumed worker writing it a second time",
                                     "cost_note": "no billed call was made: this is the conformance list"})
    ck(not again,
       "a cell already in a TERMINAL state is NOT overwritten, and the attempt returns "
       "False -- which is what makes a resumed worker harmless rather than destructive")
    ck(backend.read_grid_cells(gid) and
       {(c["document_id"], c["column_name"]): c
        for c in backend.read_grid_cells(gid)}[(DOC_A, "governing law")]["state"]
       == "FOUND",
       "...and the first answer survives the second attempt")
    forced = backend.write_grid_cell({"grid_id": gid, "document_id": DOC_A,
                                      "column_name": "governing law", "state": "NOT_FOUND",
                                      "reason": "a deliberate correction by a person",
                                      "cost_note": "no billed call was made: this is the conformance list"},
                                     if_pending=False)
    ck(forced, "...while if_pending=False overwrites, for a deliberate correction")

    _N = {"cost_note": "no billed call was made: this is the conformance list"}
    for bad, why in (
        ({"grid_id": gid, "document_id": DOC_B, "column_name": "governing law",
          "state": "FOUND", "value": "India", "quote": "short", **_N},
         "a FOUND cell whose quote is under 8 characters"),
        ({"grid_id": gid, "document_id": DOC_B, "column_name": "governing law",
          "state": "FOUND", "value": "", "quote": "governed by the laws of India", **_N},
         "a FOUND cell with no value"),
        ({"grid_id": gid, "document_id": DOC_B, "column_name": "governing law",
          "state": "NOT_FOUND", "value": "India", "reason": "a long enough reason", **_N},
         "a NOT_FOUND cell carrying a value"),
        ({"grid_id": gid, "document_id": DOC_B, "column_name": "governing law",
          "state": "NOT_FOUND", "reason": "no", **_N},
         "a NOT_FOUND cell whose reason is two characters"),
        # ── 013: the cost rules, on both backends ───────────────────────────
        ({"grid_id": gid, "document_id": DOC_B, "column_name": "term end",
          "state": "NOT_FOUND", "reason": "a long enough reason", "provider": "azure",
          "cost_inr": 0.0, "cost_note": "a recorded zero"},
         "a BILLED provider recording 0.00, which claims the call was free"),
        ({"grid_id": gid, "document_id": DOC_B, "column_name": "term end",
          "state": "NOT_FOUND", "reason": "a long enough reason", "cost_inr": -1.0,
          "cost_note": "negative"},
         "a negative cost"),
        ({"grid_id": gid, "document_id": DOC_B, "column_name": "term end",
          "state": "NOT_FOUND", "reason": "a long enough reason"},
         "a cell that RAN with neither a cost nor a note saying why there is none"),
    ):
        try:
            backend.write_grid_cell(dict(bad))
            ck(False, f"{why} is refused")
        except StoreError:
            ck(True, f"refused: {why}")
    try:
        backend.write_grid_cell({"grid_id": str(_uuid.uuid4()), "document_id": DOC_A,
                                 "column_name": "x", "state": "FOUND", "value": "v",
                                 "quote": "a long enough quote"})
        ck(False, "a cell for a grid that does not exist is refused")
    except Exception:
        ck(True, "a cell for a grid that does not exist is refused")

    ck(backend.cancel_grid(gid), "a grid is cancelled")
    ck(backend.read_grid(gid).get("cancelled_at"), "...and says so when read back")
    ck(len(backend.read_grid_cells(gid)) == 4,
       "**cancelling deletes nothing**: all four cells survive, because a lawyer who "
       "cancels at cell 30 of 40 still wants the 29 answers")
    ck(not backend.cancel_grid(str(_uuid.uuid4())),
       "cancelling an unknown grid is False, not a silent success")

    # ── H3: drafts, on BOTH backends ────────────────────────────────────────
    did = str(_uuid.uuid4())
    backend.write_draft({"draft_id": did, "kind": "agm_notice",
                         "title": "Notice of AGM"})
    ck(backend.read_draft(did)["title"] == "Notice of AGM",
       "a draft is written and read back")
    ck(backend.read_draft(str(_uuid.uuid4())) is None,
       "...and an unknown draft reads as None")
    v1 = backend.append_draft_version(
        {"draft_id": did, "title": "Notice of AGM", "body": "Notice is hereby given.",
         "slots": [{"name": "venue", "type": "MODEL_SUGGESTION"}], "blocking_count": 1})
    v2 = backend.append_draft_version(
        {"draft_id": did, "title": "Updated notice of AGM",
         "body": "Notice is hereby given to the members.",
         "slots": [{"name": "venue", "type": "USER_FACT"}], "blocking_count": 0})
    ck((v1, v2) == (1, 2), f"versions number themselves 1 then 2 ({v1}, {v2})")
    vs = backend.read_draft_versions(did)
    ck([v["version"] for v in vs] == [1, 2], "...and read back in order")
    ck(vs[0]["body"] == "Notice is hereby given.",
       "**version 1 is unchanged by the second save** -- append-only is the feature")
    ck(all(set(v) >= set(DRAFT_VERSION_KEYS) for v in vs),
       f"...every version has every key on both backends ({sorted(vs[0])})")
    ck(vs[0]["blocking_count"] == 1 and vs[1]["blocking_count"] == 0,
       "...and the blocking count survives the round trip")
    # Measured on THIS draft, not the tenant's whole inbox: scripts/rls_integration.py
    # seeds a draft into the same tenant so its isolation checks never measure an empty
    # table, and "the inbox holds exactly one draft" only ever held on an empty dict.
    inbox = backend.list_drafts(limit=10)
    mine = [d for d in inbox if str(d["draft_id"]) == did]
    ck(len(mine) == 1 and mine[0]["version"] == 2 and mine[0]["blocking_count"] == 0
       and mine[0]["title"] == "Updated notice of AGM"
       and all("body" not in d for d in inbox),
       "the draft inbox returns latest metadata only and never returns document text")
    after = backend.list_drafts(limit=10, before_updated_at=mine[0]["updated_at"],
                                before_draft_id=did) if mine else None
    ck(after is not None and all((d["updated_at"], str(d["draft_id"]))
                                 < (mine[0]["updated_at"], did) for d in after),
       "a keyset cursor after a draft returns only drafts strictly before it")
    did2 = str(_uuid.uuid4())
    backend.write_draft({"draft_id": did2, "kind": "unknown", "title": "Second draft"})
    backend.append_draft_version({"draft_id": did2, "title": "Second draft", "body": "private text",
                                  "slots": [], "blocking_count": 0})
    first_page = backend.list_drafts(limit=1)
    second_page = backend.list_drafts(
        limit=1, before_updated_at=first_page[0]["updated_at"],
        before_draft_id=first_page[0]["draft_id"])
    ck(len(first_page) == len(second_page) == 1
       and first_page[0]["draft_id"] != second_page[0]["draft_id"]
       and "body" not in first_page[0] and "body" not in second_page[0],
       "keyset pagination is bounded, has no overlap for tied timestamps, and keeps text private")

    try:
        backend.append_draft_version(
            {"draft_id": did, "version": 1, "title": "t", "body": "b",
             "slots": [], "blocking_count": 0})
        ck(False, "a version number already used is refused")
    except StoreError as e:
        ck("already has version" in str(e) or "refused" in str(e),
           "re-using a version number is REFUSED (012's primary key): two concurrent saves "
           "cannot both be version 3, and the loser is told rather than overwriting")
    ck(len(backend.read_draft_versions(did)) == 2,
       "...and the refused save wrote nothing")

    for bad, why in (
        ({"draft_id": did, "title": "t", "slots": [], "blocking_count": 1,
          "approved_by": "A. Reviewer", "approved_at": "2026-10-01T10:00:00+05:30"},
         "a version APPROVED while a slot still blocks approval"),
        ({"draft_id": did, "title": "t", "slots": [], "blocking_count": 0,
          "approved_by": "A. Reviewer"}, "an approval with no time"),
        ({"draft_id": did, "title": "t", "slots": [], "blocking_count": 0,
          "approved_by": "   ", "approved_at": "2026-10-01T10:00:00+05:30"},
         "an unattributed approval"),
        ({"draft_id": did, "title": "", "slots": [], "blocking_count": 0}, "no title"),
    ):
        try:
            backend.append_draft_version(dict(bad))
            ck(False, f"{why} is refused")
        except StoreError:
            ck(True, f"refused: {why}")
    ok3 = backend.append_draft_version(
        {"draft_id": did, "title": "t", "body": "b", "slots": [], "blocking_count": 0,
         "approved_by": "A. Reviewer", "approved_at": "2026-10-01T10:00:00+05:30"})
    ck(ok3 == 3 and backend.read_draft_versions(did)[2]["approved_by"] == "A. Reviewer",
       "...while an approval with blocking_count 0 IS stored, with its reviewer")
    try:
        backend.append_draft_version({"draft_id": str(_uuid.uuid4()), "title": "t",
                                      "slots": [], "blocking_count": 0})
        ck(False, "a version for a draft that does not exist is refused")
    except Exception:
        ck(True, "a version for a draft that does not exist is refused")

    # ── 017: the CAL-1 nonconformity score ──────────────────────────────────
    _nc = str(_uuid.uuid4())
    backend.write_run({"id": _nc, "intent": "ask", "status": "ANSWERED", "steps": [],
                       "propositions": [], "nonconformity": 0.7,
                       "nonconformity_note": "8/10 byte-matched AND entailed, 1 escalation"})
    _ncrow = backend.read_run(_nc) or {}
    ck(_ncrow.get("nonconformity") == 0.7 and "escalation" in
       str(_ncrow.get("nonconformity_note") or ""),
       f"the nonconformity score and its reason round-trip on both backends "
       f"({_ncrow.get('nonconformity')})")
    ck(isinstance(_ncrow.get("nonconformity"), float),
       f"...as a float on both, not Decimal on one "
       f"({type(_ncrow.get('nonconformity')).__name__})")
    _nn = str(_uuid.uuid4())
    backend.write_run({"id": _nn, "intent": "ask", "status": "REFUSED",
                       "refusal_code": "NO_MODEL", "steps": [], "propositions": []})
    ck((backend.read_run(_nn) or {}).get("nonconformity") is None,
       "a run with no score reads back NULL, which means NOT COMPUTED -- and is not the "
       "same as 0, which means every sentence was supported with no escalation")

    # ── 016: was the critic on when this run was written? ───────────────────
    import os as _os
    _cwas = _os.environ.pop("CRITIC_ENABLED", None)
    try:
        _os.environ["CRITIC_ENABLED"] = "true"
        _cr_on = str(_uuid.uuid4())
        backend.write_run({"id": _cr_on, "intent": "ask", "status": "PLANNED",
                           "steps": [], "propositions": []})
        _os.environ["CRITIC_ENABLED"] = "false"
        _cr_off = str(_uuid.uuid4())
        backend.write_run({"id": _cr_off, "intent": "ask", "status": "PLANNED",
                           "steps": [], "propositions": []})
        ck((backend.read_run(_cr_on) or {}).get("critic_enabled") is True
           and (backend.read_run(_cr_off) or {}).get("critic_enabled") is False,
           f"every run records whether the CRITIC was on when it was written, on both "
           f"backends -- 'the critic found nothing' and 'the critic was off' are the same "
           f"clean answer afterwards, and without this nothing tells them apart "
           f"({(backend.read_run(_cr_on) or {}).get('critic_enabled')} / "
           f"{(backend.read_run(_cr_off) or {}).get('critic_enabled')})")
    finally:
        _os.environ.pop("CRITIC_ENABLED", None)
        if _cwas is not None:
            _os.environ["CRITIC_ENABLED"] = _cwas

    # ── O8: failure tagging, on both backends ───────────────────────────────
    _fr = str(_uuid.uuid4())
    backend.write_run({"id": _fr, "intent": "research_question", "status": "PLANNED",
                       "steps": [], "propositions": []})
    backend.set_run(_fr, status="FAILED",
                    result={"error": "ConnectionResetError: reset by peer"})
    _frow = backend.read_run(_fr)
    ck(_frow and _frow.get("failure_category") == "transport",
       f"a FAILED run is TAGGED by set_run on both backends -- the one function every "
       f"terminal write routes through ({(_frow or {}).get('failure_category')})")
    ck(_frow and str(_frow.get("failure_reason") or "").strip(),
       "...and the reason is stored with it: a bare word in a weekly report is a number "
       "nobody can check")
    _ar = str(_uuid.uuid4())
    backend.write_run({"id": _ar, "intent": "research_question", "status": "PLANNED",
                       "steps": [], "propositions": []})
    backend.set_run(_ar, status="ANSWERED", result={"answer": "x"})
    ck((backend.read_run(_ar) or {}).get("failure_category") is None,
       "an ANSWERED run carries NO category: a success with a failure word on it would be "
       "counted as a failure by every query that follows")
    _counts = backend.read_failure_counts()
    ck(isinstance(_counts, list) and all(set(r) == {"week", "category", "count"}
                                         for r in _counts),
       f"read_failure_counts returns week/category/count rows on both backends "
       f"({_counts[:1]})")
    ck(any(r["category"] == "transport" and r["count"] >= 1 for r in _counts),
       "...including the run just tagged")
    ck(not any(r["category"] is not None and r["category"] == "" for r in _counts),
       "...and an untagged run reads as category None, never an empty string")

    # ── V1: the vault, on both backends ─────────────────────────────────────
    _vm = str(_uuid.uuid4())
    backend.write_matter({"matter_id": _vm, "name": f"vault matter {_vm[:8]}"},
                         owner=getattr(backend, "_session_actor", None) or None)
    _vd = str(_uuid.uuid4())
    backend.write_vault_document({
        "document_id": _vd, "matter_id": _vm, "sha256": "a" * 64, "name": "NDA.pdf",
        "byte_count": 2048, "state": "INGESTED", "doc_class": "nda",
        "class_reason": "nda on 6 points", "text_chars": 1200})
    _got = backend.read_vault_document(_vd) or {}
    ck(_got.get("doc_class") == "nda" and _got.get("text_chars") == 1200,
       f"a vault document round-trips with its class and text length "
       f"({_got.get('doc_class')})")
    ck(backend.read_vault_document(str(_uuid.uuid4())) is None,
       "...and an unknown one reads as None")

    for bad, why in (
            ({"document_id": str(_uuid.uuid4()), "matter_id": _vm, "sha256": "zz",
              "name": "x", "byte_count": 1}, "a sha256 that is not one"),
            ({"document_id": str(_uuid.uuid4()), "matter_id": _vm, "sha256": "b" * 64,
              "name": "  ", "byte_count": 1}, "a document with no name"),
            ({"document_id": str(_uuid.uuid4()), "matter_id": _vm, "sha256": "c" * 64,
              "name": "x", "byte_count": 1, "doc_class": "nda"},
             "a class with no reason"),
            ({"document_id": str(_uuid.uuid4()), "matter_id": _vm, "sha256": "d" * 64,
              "name": "x", "byte_count": 1, "state": "DELETED", "text_chars": 10},
             "a DELETED document that still carries text")):
        try:
            backend.write_vault_document(bad)
            ck(False, f"{why} is refused")
        except StoreError:
            ck(True, f"refused on both backends: {why}")

    # Dedupe is per tenant: the same bytes twice is one document.
    try:
        backend.write_vault_document({
            "document_id": str(_uuid.uuid4()), "matter_id": _vm, "sha256": "a" * 64,
            "name": "NDA (copy).pdf", "byte_count": 2048})
        ck(False, "the same bytes twice is refused")
    except DuplicateVaultDocument as dup:
        ck(True, "**the same bytes twice is ONE document**: dedupe is a constraint, not a "
                 "check the caller remembers")
        ck(dup.document_id == _vd,
           f"...and the refusal names the document already holding those bytes, so an "
           f"upload can return it ({dup.document_id} vs {_vd})")

    ck(backend.write_vault_chunks(_vd, ["2. Term\n\nThe term is five years.",
                                        "7. Governing law\n\nIndia."]) == 2,
       "chunks are written")
    _chunks = [c for c in backend.read_vault_chunks() if c["document_id"] == _vd]
    ck(len(_chunks) == 2 and _chunks[0]["name"] == "NDA.pdf"
       and _chunks[0]["doc_class"] == "nda",
       f"...and read back WITH the document's name and class, which is what the "
       f"contextual index needs ({len(_chunks)})")
    try:
        backend.write_vault_chunks(_vd, ["ok", "   "])
        ck(False, "an empty chunk is refused")
    except StoreError:
        ck(True, "an empty chunk is refused (020 vault_chunks.text)")

    ck(backend.write_vault_tags(_vd, [
        {"tag": "Term", "quote": "The term is five years."}]) == 1, "a tag is written")
    ck([t["tag"] for t in backend.read_vault_tags(_vd)] == ["Term"],
       "...and reads back")
    try:
        backend.write_vault_tags(_vd, [{"tag": "Term", "quote": "short"}])
        ck(False, "a tag with a 5-character quote is refused")
    except StoreError:
        ck(True, "a tag whose quote is under 8 characters is REFUSED: a tag with no span "
                 "is an assertion about a document nobody can check against it")

    _listed = backend.list_vault_documents(matter_id=_vm)
    ck([d["document_id"] for d in _listed] == [_vd],
       f"a matter's documents list ({len(_listed)})")
    try:
        backend.list_vault_documents(matter_id="")
        ck(False, "listing with no matter is refused")
    except StoreError:
        ck(True, "listing vault documents with NO matter is refused, exactly as "
                 "conversations are (8b)")

    _counts = backend.vault_counts()
    ck(_counts["documents"] >= 1 and _counts["by_state"].get("INGESTED", 0) >= 1,
       f"vault_counts reports what is there ({_counts['by_state']})")

    # ── deletion keeps the row and removes everything searchable ───────────
    ck(backend.delete_vault_document(_vd, now="2026-10-02T00:00:00+00:00"),
       "a document is deleted")
    _after = backend.read_vault_document(_vd) or {}
    ck(_after.get("state") == "DELETED" and _after.get("deleted_at"),
       f"**the ROW survives, marked DELETED with a date**: 'we never had it' and 'we had "
       f"it and destroyed it on 4 March' are different answers to a regulator "
       f"({_after.get('state')})")
    ck(_after.get("text_chars") is None,
       "...and it carries no text length any more")
    ck(not [c for c in backend.read_vault_chunks() if c["document_id"] == _vd],
       "...its chunks are gone, so nothing searchable survives")
    ck(not backend.read_vault_tags(_vd), "...and its tags are gone")
    ck(not backend.list_vault_documents(matter_id=_vm),
       "...and it is absent from the matter's listing")
    ck(not backend.delete_vault_document(_vd, now="2026-10-02T00:00:00+00:00"),
       "deleting it again returns False rather than claiming to be the first")
    # An ingest that read the row BEFORE the delete finishes AFTER it, with exactly the
    # writes agents/vault_ingest makes. None of them may bring the document back.
    _late = backend.write_vault_document({
        "document_id": _vd, "matter_id": _vm, "sha256": "a" * 64, "name": "NDA.pdf",
        "byte_count": 2048, "state": "INGESTED", "doc_class": "nda",
        "class_reason": "nda on 6 points", "text_chars": 1200}) or {}
    _late_chunks = backend.write_vault_chunks(_vd, ["2. Term\n\nThe term is five years."])
    _late_tags = backend.write_vault_tags(_vd, [
        {"tag": "Term", "quote": "The term is five years."}])
    _after = backend.read_vault_document(_vd) or {}
    ck(_after.get("state") == "DELETED" and _after.get("deleted_at")
       and _after.get("text_chars") is None and _late.get("state") == "DELETED",
       f"**a late ingest's final write does not revive a DELETED document** "
       f"({_after.get('state')}, returned {_late.get('state')})")
    ck(_late_chunks == 0 and _late_tags == 0
       and not [c for c in backend.read_vault_chunks() if c["document_id"] == _vd]
       and not backend.read_vault_tags(_vd),
       f"...nor store its text again as chunks or tags ({_late_chunks}, {_late_tags})")

    # ── 8b: matters, and NO CROSS-MATTER LISTING ────────────────────────────
    _m1, _m2 = str(_uuid.uuid4()), str(_uuid.uuid4())
    backend.write_matter({"matter_id": _m1, "name": "Acme acquisition",
                          "client_ref": "ACM-1"},
                         owner=getattr(backend, "_session_actor", None) or None)
    backend.write_matter({"matter_id": _m2, "name": "Beta dispute"},
                         owner=getattr(backend, "_session_actor", None) or None)
    _names = [m["name"] for m in backend.list_matters()]
    ck({"Acme acquisition", "Beta dispute"} <= set(_names)
       and _names == sorted(_names, key=str.lower),
       f"matters round-trip and list in name order ({_names})")
    try:
        backend.write_matter({"matter_id": str(_uuid.uuid4()), "name": "acme ACQUISITION"})
        ck(False, "a duplicate matter name is refused")
    except StoreError:
        ck(True, "a duplicate matter name is refused case-insensitively on both backends")
    try:
        backend.write_matter({"matter_id": str(_uuid.uuid4()), "name": "  "})
        ck(False, "a nameless matter is refused")
    except StoreError:
        ck(True, "a matter with no name is refused")

    _ca, _cb = str(_uuid.uuid4()), str(_uuid.uuid4())
    backend.write_conversation({"conversation_id": _ca, "title": "on Acme",
                                "matter_id": _m1})
    backend.write_conversation({"conversation_id": _cb, "title": "on Beta",
                                "matter_id": _m2})
    _listed = backend.list_conversations(matter_id=_m1)
    ck([r["conversation_id"] for r in _listed] == [_ca],
       f"**listing one matter returns only that matter's conversations** "
       f"({[r['title'] for r in _listed]})")
    ck([r["conversation_id"] for r in backend.list_conversations(matter_id=_m2)] == [_cb],
       "...and the other matter returns only its own")
    for bad in ("", None, "   "):
        try:
            backend.list_conversations(matter_id=bad)
            ck(False, f"listing with matter_id={bad!r} is refused")
        except StoreError:
            ck(True, f"listing with matter_id={bad!r} is REFUSED -- there is deliberately "
                     f"no value meaning 'all matters', because a listing that can be "
                     f"called without a scope will be")
    _unfiled = str(_uuid.uuid4())
    backend.write_conversation({"conversation_id": _unfiled, "title": "not filed"})
    ck(_unfiled not in [r["conversation_id"]
                        for r in backend.list_conversations(matter_id=_m1)],
       "a conversation with NO matter is not returned by any matter's listing: NULL is "
       "its own bucket, never 'belongs to whichever matter you asked for'")

    # ── 8a: users, roles and invites, on both backends ──────────────────────
    import hashlib as _hl
    _ad = str(_uuid.uuid4())
    backend.write_actor({"actor_id": _ad, "label": "admin", "role": "admin",
                         "email": "admin@example.com"})
    _arow = backend.read_actor(_ad) or {}
    ck(_arow.get("role") == "admin" and _arow.get("email") == "admin@example.com",
       f"an actor round-trips with its role and email ({_arow.get('role')})")
    ck(backend.read_actor(str(_uuid.uuid4())) is None,
       "...and an unknown actor reads as None")
    for bad, why in (({"actor_id": str(_uuid.uuid4()), "role": "superuser"},
                      "a role that is not one of the three"),
                     ({"actor_id": str(_uuid.uuid4()), "role": "viewer",
                       "password_hash": "d41d8cd98f00b204e9800998ecf8427e"},
                      "a bare digest as a password hash")):
        try:
            backend.write_actor(bad)
            ck(False, f"{why} is refused")
        except StoreError:
            ck(True, f"refused on both backends: {why}")

    _tok = _hl.sha256(b"a-real-token").hexdigest()
    _iid = str(_uuid.uuid4())
    backend.create_invite({"invite_id": _iid, "email": "new@example.com",
                           "role": "lawyer", "token_hash": _tok, "invited_by": _ad,
                           "expires_at": "2099-01-01T00:00:00+00:00"})
    try:
        backend.create_invite({"invite_id": str(_uuid.uuid4()),
                               "email": "new@example.com", "role": "viewer",
                               "token_hash": _hl.sha256(b"other").hexdigest(),
                               "invited_by": _ad,
                               "expires_at": "2099-01-01T00:00:00+00:00"})
        ck(False, "a second LIVE invite for one email is refused")
    except StoreError:
        ck(True, "a second LIVE invite for one email is refused on both backends")

    _joiner = str(_uuid.uuid4())
    backend.write_actor({"actor_id": _joiner, "label": "joiner", "role": "lawyer"})
    _first = backend.accept_invite(_tok, actor_id=_joiner, now="2026-10-02T00:00:00+00:00")
    ck(_first and _first.get("role") == "lawyer",
       f"an invite is accepted once, and carries the role it was issued for "
       f"({(_first or {}).get('role')})")
    _second = backend.accept_invite(_tok, actor_id=_joiner,
                                    now="2026-10-02T00:00:00+00:00")
    ck(_second is None,
       "**the same token cannot be used twice** -- single use is the database's job, not "
       "a handler's: on Postgres the UPDATE carries `accepted_at IS NULL`, so two "
       "simultaneous accepts cannot both win")
    # The shape invites.accept uses: the account is created BY the accept, atomically.
    # (The checks above write the actor first, which is why they never caught that the verb
    # stamped invites.accepted_by -- a foreign key -- before its actor existed.)
    _tok3 = _hl.sha256(b"atomic-accept").hexdigest()
    backend.create_invite({"invite_id": str(_uuid.uuid4()), "email": "atomic@example.com",
                           "role": "lawyer", "token_hash": _tok3, "invited_by": _ad,
                           "expires_at": "2099-01-01T00:00:00+00:00"})
    _new = str(_uuid.uuid4())
    _acc = backend.accept_invite(_tok3, actor_id=_new, now="2026-10-02T00:00:00+00:00",
                                 actor={"label": "atomic", "role": "lawyer",
                                        "email": "atomic@example.com"})
    ck(_acc is not None and (backend.read_actor(_new) or {}).get("role") == "lawyer",
       "an accept that CREATES its account succeeds on both backends, account and all")
    _late = str(_uuid.uuid4())
    ck(backend.accept_invite(_tok3, actor_id=_late, now="2026-10-02T00:00:00+00:00",
                             actor={"label": "late", "role": "lawyer",
                                    "email": "atomic@example.com"}) is None
       and backend.read_actor(_late) is None,
       "...and a refused second accept leaves NO second account behind")
    # An invite that EXPIRES while we watch. It cannot be created already-expired: 018's
    # invites_expires_after_creation forbids that, correctly -- an invite dated into the
    # past is not an expired invite, it is a nonsense row. So this one is given a second
    # to live, and the second is allowed to pass. Postgres compares against its own
    # clock, which is why real time has to elapse rather than a `now` being passed in.
    import datetime as _dt
    import time as _time
    _soon = (_dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(seconds=1)).isoformat()
    _expired = _hl.sha256(b"expiring-token").hexdigest()
    backend.create_invite({"invite_id": str(_uuid.uuid4()), "email": "old@example.com",
                           "role": "viewer", "token_hash": _expired, "invited_by": _ad,
                           "expires_at": _soon})
    _time.sleep(1.2)
    ck(backend.accept_invite(_expired, actor_id=_joiner,
                             now=_dt.datetime.now(_dt.timezone.utc).isoformat()) is None,
       "an EXPIRED invite cannot be accepted: a credential with no horizon is the one "
       "that gets used by whoever buys the laptop")
    ck(backend.accept_invite(_hl.sha256(b"never-issued").hexdigest(), actor_id=_joiner,
                             now="2026-10-02T00:00:00+00:00") is None,
       "...and an unknown token gets the SAME answer as a used or expired one, so a "
       "token cannot be probed to learn which it was")

    # ── 036: pending invites, cancel (marks, never deletes), on both backends ─
    _ptok = _hl.sha256(b"pending-token-036").hexdigest()
    _pid = str(_uuid.uuid4())
    backend.create_invite({"invite_id": _pid, "email": "pending036@example.com",
                           "role": "viewer", "token_hash": _ptok, "invited_by": _ad,
                           "expires_at": "2099-01-01T00:00:00+00:00"})
    _pend = {i["invite_id"]: i for i in backend.list_pending_invites()}
    ck(_pid in _pend and _pend[_pid]["email"] == "pending036@example.com"
       and _pend[_pid]["role"] == "viewer" and bool(_pend[_pid].get("created_at")),
       "036: a live invite is listed as pending, with its email, role and when it was made")
    ck(all("token_hash" not in i and "token" not in i for i in _pend.values()),
       "...and NO pending row carries the token or its hash")
    ck(_iid not in _pend and not any(i["email"] in ("atomic@example.com", "old@example.com")
                                     for i in _pend.values()),
       "...and accepted and expired invites are not pending")
    ck(backend.cancel_invite(_pid, cancelled_by=_ad) is True,
       "an admin cancels a pending invite")
    ck(_pid not in {i["invite_id"] for i in backend.list_pending_invites()},
       "...and it leaves the pending list")
    ck(backend.cancel_invite(_pid, cancelled_by=_ad) is False,
       "...and cancelling it again changes nothing (False)")
    ck(backend.accept_invite(_ptok, actor_id=str(_uuid.uuid4()),
                             now="2026-10-02T00:00:00+00:00",
                             actor={"label": "x", "role": "viewer",
                                    "email": "pending036@example.com"}) is None,
       "**a CANCELLED invite cannot be accepted**, and gets the same None as a used one")
    ck(backend.cancel_invite(_iid, cancelled_by=_ad) is False,
       "an ACCEPTED invite cannot be cancelled")
    ck(backend.cancel_invite(str(_uuid.uuid4()), cancelled_by=_ad) is False
       and backend.cancel_invite("not-a-uuid", cancelled_by=_ad) is False,
       "an unknown or malformed invite id cancels nothing, and does not raise")
    _rtok = _hl.sha256(b"reinvite-036").hexdigest()
    try:
        backend.create_invite({"invite_id": str(_uuid.uuid4()),
                               "email": "pending036@example.com", "role": "lawyer",
                               "token_hash": _rtok, "invited_by": _ad,
                               "expires_at": "2099-01-01T00:00:00+00:00"})
        ck(True, "cancelling an invite frees the email for a fresh one")
    except StoreError:
        ck(False, "cancelling an invite frees the email for a fresh one")
    # The invite from the expiry check above is still unused; re-inviting that email must
    # retire it, not fail on invites_live_per_email_idx forever.
    try:
        backend.create_invite({"invite_id": str(_uuid.uuid4()), "email": "old@example.com",
                               "role": "viewer",
                               "token_hash": _hl.sha256(b"reinvite-expired").hexdigest(),
                               "invited_by": _ad,
                               "expires_at": "2099-01-01T00:00:00+00:00"})
        ck(True, "an EXPIRED unused invite does not block re-inviting that email")
    except StoreError:
        ck(False, "an EXPIRED unused invite does not block re-inviting that email")
    _people = {a["actor_id"]: a for a in backend.list_actors()}
    ck(_ad in _people and bool(_people[_ad].get("created_at"))
       and all("password_hash" not in a for a in _people.values()),
       "list_actors gives when each person joined, and never a password hash")

    # ── O9: the answer cache, on both backends ──────────────────────────────
    _LK, _CK = "a" * 64, "b" * 64
    _CIT = [{"id": "c1", "provision": "s.96", "sha256": "c" * 64, "quote": "a quote"}]
    ck(backend.read_cache_entry(_LK) is None,
       "an unknown cache key reads as None, not an empty entry")
    ck(backend.write_cache_entry(
        {"lookup_key": _LK, "content_key": _CK, "question": "When is the AGM?",
         "task": "RESEARCH_QUESTION", "as_of": "2026-10-01", "sources": ["held"],
         "citations": _CIT, "payload": {"status": "ANSWERED"},
         "created_at": "2026-10-01T10:00:00+05:30"}),
       "a cache entry is written")
    _got = backend.read_cache_entry(_LK)
    ck(_got and _got["content_key"] == _CK and _got["question"] == "When is the AGM?",
       "...and reads back with its content key and question")
    ck(_got and [c["id"] for c in _got["citations"]] == ["c1"]
       and _got["citations"][0]["sha256"] == "c" * 64,
       "...and its CITATIONS survive the round trip, which is the whole point: without "
       "them the entry can never be re-verified")
    ck(_got and _got["payload"].get("status") == "ANSWERED"
       and isinstance(_got["sources"], list),
       "...with the payload as an object and sources as a list on both backends")
    ck(backend.write_cache_entry(
        {"lookup_key": _LK, "content_key": "d" * 64, "question": "When is the AGM?",
         "task": "RESEARCH_QUESTION", "as_of": "2026-10-01", "sources": ["held"],
         "citations": _CIT, "payload": {"status": "ANSWERED"},
         "created_at": "2026-10-01T11:00:00+05:30"}),
       "writing the same key again UPDATES it: a re-answer replaces the entry rather than "
       "conflicting, because the newer reading of the law is the one to keep")
    ck((backend.read_cache_entry(_LK) or {}).get("content_key") == "d" * 64,
       "...and the newer content key is what reads back")
    try:
        backend.write_cache_entry(
            {"lookup_key": "e" * 64, "content_key": _CK, "question": "q", "task": "t",
             "as_of": "2026-10-01", "sources": [], "citations": [],
             "payload": {}, "created_at": "2026-10-01T10:00:00+05:30"})
        ck(False, "an entry citing NOTHING is refused")
    except StoreError:
        ck(True, "an entry citing NOTHING is refused on both backends: it could only ever "
                 "be rejected on read, so storing it is storing a row with no use")

    # Measured as DELTAS, not against zero: this list also runs against a live database
    # that scripts/rls_integration.py has already seeded, and an absolute assertion made
    # the conformance fail on Postgres for a reason that had nothing to do with the
    # backend. A conformance check that only holds on an empty table is not a conformance
    # check.
    _before = backend.read_cache_stats()
    ck(set(_before) == {"hits", "misses", "stale"},
       f"cache statistics report the same three names on both backends ({sorted(_before)})")
    backend.bump_cache_stat("hits", day="2026-10-01")
    backend.bump_cache_stat("hits", day="2026-10-01")
    backend.bump_cache_stat("stale", day="2026-10-02")
    backend.bump_cache_stat("misses", day="2026-10-02")
    _st = backend.read_cache_stats()
    _delta = {k: _st[k] - _before[k] for k in _before}
    ck(_delta == {"hits": 2, "misses": 1, "stale": 1},
       f"...and accumulate ACROSS DAYS, upserting rather than conflicting ({_delta})")
    try:
        backend.bump_cache_stat("hit", day="2026-10-01")
        ck(False, "an unknown statistic name is refused")
    except StoreError:
        ck(True, "an unknown statistic name is refused -- the name reaches a column, and a "
                 "fixed tuple is what keeps that safe")


    # ── T3 move 10: document_checks (023), against BOTH backends ────────────
    # This list has caught five "wrote it, didn't select it" divergences. The append-only
    # shape and the latest-per-document renewal filter are exactly the kind of thing that
    # works in a dict and not in SQL, so they are asserted here rather than in either
    # backend's own suite.
    from checker import doc_validity as _dval
    from checker import doc_verification as _dver

    _dc_doc = str(_uuid.uuid4())
    backend.write_vault_document({"document_id": _dc_doc, "matter_id": None,
                                  "sha256": _uuid.uuid4().hex + _uuid.uuid4().hex,
                                  "name": "cert.pdf", "byte_count": 10,
                                  "state": "INGESTED"})
    _dc_first = backend.write_document_check({
        "check_id": str(_uuid.uuid4()), "document_id": _dc_doc, "as_of": "2026-03-01",
        "checked_at": "2026-03-01T00:00:00Z",
        "verification_status": _dver.INCOMPLETE, "validity_status": _dval.EXPIRES_ON,
        "action": _dval.RENEW_BY, "renew_by": "2026-05-01",
        "action_reason": "in force and the period ends inside the window the calendar shows",
        "expires_on": "2026-05-01",
        "law_versions": {"corpus/companies_act/1283.json": "a" * 40}})
    ck(_dc_first.get("action") == _dval.RENEW_BY
       and _dc_first.get("renew_by") == "2026-05-01",
       f"a document check is written and READ BACK with its action and renewal date "
       f"({_dc_first.get('action')}, {_dc_first.get('renew_by')})")
    ck(_dc_first.get("law_versions") == {"corpus/companies_act/1283.json": "a" * 40},
       f"...and the law_versions map survives the round trip, in the same identity `runs` "
       f"uses ({_dc_first.get('law_versions')})")

    _dc_rows = backend.read_document_checks(document_id=_dc_doc)
    ck(len(_dc_rows) == 1, f"one check, one row ({len(_dc_rows)})")

    # APPEND, never overwrite. The architect record's first reason: "a certificate valid in
    # March is expired in October, and the same bytes produce a different action".
    backend.write_document_check({
        "check_id": str(_uuid.uuid4()), "document_id": _dc_doc, "as_of": "2026-10-05",
        "checked_at": "2026-10-05T00:00:00Z",
        "verification_status": _dver.INCOMPLETE, "validity_status": _dval.EXPIRED,
        "action": _dval.REPLACE,
        "action_reason": "the validity period ran out and nobody said this class renews"})
    _dc_rows = backend.read_document_checks(document_id=_dc_doc)
    ck(len(_dc_rows) == 2,
       f"a second check on the SAME document ADDS a row rather than replacing one -- 'what "
       f"did we tell them in March' is the question that matters when a client asks why "
       f"they were not warned ({len(_dc_rows)})")
    ck(_dc_rows[0]["action"] == _dval.REPLACE,
       f"...and the newest is first, so 'what is it now' needs no sorting by the caller "
       f"({_dc_rows[0]['action']})")

    # The renewal feed: the LATEST check decides. A renewal raised in March must not still
    # show after April's check said REPLACE.
    _ren = [r for r in backend.read_renewals() if r["document_id"] == _dc_doc]
    ck(not _ren,
       f"the March renewal no longer appears, because the latest check on that document is "
       f"REPLACE -- a bare `WHERE renew_by IS NOT NULL` would have shown every renewal ever "
       f"raised ({_ren})")

    _dc_live = str(_uuid.uuid4())
    backend.write_vault_document({"document_id": _dc_live, "matter_id": None,
                                  "sha256": _uuid.uuid4().hex + _uuid.uuid4().hex,
                                  "name": "live.pdf", "byte_count": 10,
                                  "state": "INGESTED"})
    backend.write_document_check({
        "check_id": str(_uuid.uuid4()), "document_id": _dc_live, "as_of": "2026-10-05",
        "checked_at": "2026-10-05T00:00:00Z",
        "verification_status": _dver.INCOMPLETE, "validity_status": _dval.EXPIRES_ON,
        "action": _dval.RENEW_BY, "renew_by": "2026-12-01", "expires_on": "2026-12-01",
        "action_reason": "in force and the renewal falls inside the ninety-day window"})
    _ren2 = [r for r in backend.read_renewals() if r["document_id"] == _dc_live]
    ck(len(_ren2) == 1 and _ren2[0]["renew_by"] == "2026-12-01",
       f"an outstanding renewal IS returned, so the filter above is not simply hiding "
       f"everything ({_ren2})")
    ck(not [r for r in backend.read_renewals(on_or_before="2026-11-01")
            if r["document_id"] == _dc_live],
       "...and `on_or_before` narrows it, which is how calendar.upcoming asks for a horizon")

    # 023's CHECKs, restated in both backends. A rule only Postgres enforces is a rule the
    # gate never runs.
    for _bad, _why in (
        ({"action": _dval.KEEP, "validity_status": _dval.EXPIRED,
          "verification_status": _dver.INCOMPLETE,
          "action_reason": "this should never be storable at all, not once"},
         "KEEP on an EXPIRED document"),
        ({"action": _dval.KEEP, "validity_status": _dval.CURRENT,
          "verification_status": _dver.FAILED,
          "action_reason": "this should never be storable at all, not once"},
         "KEEP when verification FAILED"),
        ({"action": _dval.RENEW_BY, "validity_status": _dval.EXPIRES_ON,
          "verification_status": _dver.INCOMPLETE,
          "action_reason": "a renewal with no date the calendar could ever show"},
         "RENEW_BY with no renew_by date"),
        ({"action": _dval.KEEP, "validity_status": _dval.CURRENT,
          "verification_status": _dver.INCOMPLETE, "renew_by": "2026-12-01",
          "action_reason": "a date on a KEEP, which would appear for a document fine as is"},
         "a renew_by date on a KEEP"),
        ({"action": _dval.KEEP, "validity_status": _dval.CURRENT,
          "verification_status": _dver.INCOMPLETE, "action_reason": "too short"},
         "an action_reason under twenty characters"),
    ):
        _row = {"check_id": str(_uuid.uuid4()), "document_id": _dc_live,
                "as_of": "2026-10-05", "checked_at": "2026-10-05T00:00:00Z", **_bad}
        try:
            backend.write_document_check(_row)
            ck(False, f"{_why} must be REFUSED by the store, and was written")
        except Exception as _e:                                  # noqa: BLE001
            ck(True, f"{_why} is refused by the store ({type(_e).__name__})")

    return out
