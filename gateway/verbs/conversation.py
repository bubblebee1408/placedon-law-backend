"""The conversation layer (C2): intake, task routing, as_of, send/get/list."""
from __future__ import annotations

import re

from gateway import access
from gateway.store import READABLE_VAULT_STATES
from gateway.verbs import documents, model_access
from gateway.verbs.answers import _envelope_for, _files_block
from gateway.verbs.ask_layers import _critic_enabled
from gateway.verbs.core import AS_OF_TASK_ONLY, Context, _law_date, _now, _refuse, _today
from gateway.verbs.drafts import DRAFT_KIND_UNKNOWN, _draft_prose


def _intake_origin(message: str):
    """A `public_only` clearance for the user's OWN TYPED WORDS.

    Finding 1 on PR #27. The classifier wraps the message in `<source>` delimiters, so
    `azure_model.narrate` -> `public_only.verify_prompt` requires an origin that block can
    clear against. The old code passed `()`, and `verify_prompt` refuses "no origin given;
    there is nothing to clear the prompt against" -- so the classifier was UNREACHABLE and
    every unmatched message came back NEEDS_CLARIFICATION for a reason that had nothing to
    do with the message.

    The right clearance is `clear_matter`, not a corpus origin, and the distinction is the
    honest one: a lawyer's question is their client's business, not published text. That
    routes it through PLAN_22 D3's gate rather than around it -- only a provider in
    MATTER_PROVIDERS may receive it, and `refuse_unconfirmed_region` will refuse a
    matter document while the region is unconfirmed (only an in-process test context can
    mark a synthetic fixture). Both of those are
    refusals we WANT: they end in a fallback to RESEARCH_QUESTION, never in a question for
    the user.

    Returns None when no clearance can be made, which the caller treats as "no model".
    """
    from checker import public_only, router
    try:
        return public_only.clear_matter(message, name="intake message",
                                        provider=router.AZURE)
    except Exception:                                           # noqa: BLE001
        return None


def _intake_classify(args: dict, ctx: Context) -> dict:
    """Which of six fixed tasks this request is. PLAN_23 layer 1.

    **It never runs the task.** No plan is compiled, no run is persisted, no run_id comes
    back -- the caller gets a name, two alternatives and a reason, and decides. That is what
    makes a misclassification cost time rather than correctness, and it is why the model
    call is router.CLASSIFICATION at LOW consequence while `ask` is NARRATION.

    ONE call to `intake.classify`, with a `model_provider` it invokes only if the rules
    cannot decide. The first version ran the rules, compared the returned RULE NAME against
    two strings to guess whether a model was wanted, obtained one, and ran the rules again
    -- which coupled this file to `agents/intake.py`'s internals and ran the rules twice.
    """
    from agents import intake

    message = args.get("message")
    if message is None:
        message = ""
    if not isinstance(message, str):
        # BAD_REQUEST, not an exception. `message.strip()` on an int is a 500, and a
        # malformed request is the caller's to fix, not an outage to page someone about.
        return _refuse("BAD_REQUEST",
                       f"message must be a string, got {type(message).__name__}")
    raw_files = args.get("files")
    if raw_files is None:
        raw_files = []
    if not isinstance(raw_files, list):
        return _refuse("BAD_REQUEST", "files must be a list of {name, type} objects")
    files = []
    for i, f in enumerate(raw_files):
        if not isinstance(f, dict):
            return _refuse("BAD_REQUEST", f"files[{i}] must be an object with name/type")
        files.append({"name": str(f.get("name") or ""), "type": str(f.get("type") or "")})
    facts = args.get("facts")
    if facts is not None and not isinstance(facts, dict):
        return _refuse("BAD_REQUEST", "facts must be an object")
    if not message.strip() and not files:
        return _refuse("BAD_REQUEST",
                       "a message or at least one file is required: there is nothing to "
                       "classify otherwise")

    unavailable: list = []

    def provider():
        """A model, or None. Called by classify() only if the rules did not decide."""
        from checker import router
        origin = _intake_origin(message)
        if origin is None:
            unavailable.append("NO_CLEARANCE")
            return None
        served, refusal = model_access._served_or_refusal(origin, name="intake.classify",
                                             purpose=router.CLASSIFICATION, ctx=ctx,
                                             consequence=router.LOW)
        if refusal:
            unavailable.append(refusal["code"])
            return None
        return served.call

    out = intake.classify(message, files=files, facts=facts,
                          model_provider=provider).to_dict()
    if unavailable:
        # Not a refusal of the verb: the rules already produced an answer, and this only
        # says the classifier could not be asked to improve on it.
        out["classifier_unavailable"] = unavailable[0]
    out["note"] = _INTAKE_NOTE
    return out


_INTAKE_NOTE = (
    "Intake names the task and never runs it. Scope is not decided here: an off-topic "
    "request still classifies, and the path it names is what refuses it -- so a question "
    "about a body of law this engine does not hold comes back from `ask` with the named "
    "refusal, not from here with silence.")


# ── C2: the conversation layer ───────────────────────────────────────────────
#
# Which verb answers each task intake names. Written here rather than inferred, and the
# two tasks with no verb are NAMED rather than omitted: an absent key would make
# "not built" indistinguishable from "forgot to wire it".
TASK_VERB: dict[str, str] = {
    "RESEARCH_QUESTION": "ask",
    "REVIEW_CONTRACT": "review_contract",
    "REVIEW_DOCUMENT": "review_document",
    "EVENT_ASSESS": "events.assess",
    # No verb exists yet. `agents/plans.py` declares the intents and nothing serves them,
    # so `conversation.send` ABSTAINS with that said in words rather than returning an
    # empty answer that reads as "no obligation found".
    "COMPANY_STANDING": "",
    "LAW_CHANGES": "",
    # H3. Served by a verb, like EVENT_ASSESS.
    "DRAFT": "draft.create",
    # H4.
    "REVIEW_TABLE": "review_table.create",
}

# Tasks whose work is long enough to belong on the queue rather than on the socket. Keyed
# to QUEUED_INTENTS so a task cannot be queued for an intent no worker serves.
TASK_INTENT: dict[str, str] = {
    "RESEARCH_QUESTION": "research_question",
    "REVIEW_CONTRACT": "review_contract",
    "REVIEW_DOCUMENT": "review_document",
}


# Job 3. Which prior turn a draft can be built from, and which template builds it.
# A task not in here cannot be a draft's source: there is no template for a review table,
# and inventing one would mean writing the law into it from somewhere else.
DRAFT_SOURCE_TASK: dict[str, str] = {"REVIEW_CONTRACT": "client_email",
                                     "RESEARCH_QUESTION": "research_memo"}


def _draft_source(cid: str, ctx: Context):
    """(template, the source run's result, run_id) for the newest turn in this thread a
    draft can be built from, or (None, None, None).

    "Draft an email to the client about this review" means THIS review -- the last one in
    this thread. Nothing is inferred from the user's words beyond the task they already
    ran, because a draft built from the wrong contract is worse than no draft.
    """
    for msg in reversed(ctx.store.read_messages(cid) or ()):
        if str(msg.get("role") or "") != "assistant":
            continue
        template = DRAFT_SOURCE_TASK.get(str(msg.get("task") or ""))
        run_id = str(msg.get("run_id") or "")
        if not template or not run_id:
            continue
        run = ctx.store.read_run(run_id) or {}
        result = run.get("result")
        if not isinstance(result, dict):
            # The run exists and has no stored result -- still running, or it failed. Keep
            # looking back: a half-finished run is not a source, and treating it as one
            # would draft from nothing and call it a summary.
            continue
        if not result.get("question"):
            # `ask` returns the answer, not the question. The run's own arguments hold it,
            # and a memo that cannot say what was asked is a memo nobody can check.
            result = dict(result,
                          question=str((run.get("args") or {}).get("question") or ""))
        return template, result, run_id
    return None, None, None


def _persist_result(ctx: Context, result: dict) -> None:
    """Record on the run what it produced, so a later turn can read it back.

    `_persist_run` writes the run, its steps and its propositions and **not its result**,
    so an inline-served run was stored as `status=ANSWERED, result=NULL` -- a row claiming
    an answer exists while keeping nothing of it. A worker-served run does store one
    (`gateway/worker.py`), so the same intent remembered different amounts depending on
    which path ran it. Job 3 needs it because a draft is built FROM a run that already
    happened, and the queued and inline paths must offer the draft the same thing.

    The status is read back and written unchanged: this records a result, it never decides
    one.
    """
    if ctx.store is None:
        return
    run_id = str(result.get("run_id") or "")
    if not run_id:
        return
    row = ctx.store.read_run(run_id)
    if row is None or row.get("result") is not None:
        return
    ctx.store.set_run(run_id, status=str(row.get("status") or "ANSWERED"),
                      refusal_code=row.get("refusal_code"),
                      result={k: v for k, v in result.items() if k != "run_id"})


MAX_CONVERSATION_CHARS = 8000
MAX_CONVERSATION_FILES = 20


def _turn_metadata(metadata: dict, result: dict) -> dict:
    """Retrieval and artifact provenance lives beside the frozen legal envelope."""
    out = dict(metadata)
    if isinstance(result.get("sources"), dict):
        out["sources"] = result["sources"]
    # company_facts: which stored or sent facts an EVENT_ASSESS turn used, so the saved
    # message still says why a body (e.g. SEBI for a listed firm) was engaged.
    for key in ("document_summary", "document_evidence", "document_summary_unavailable",
                "law_as_of", "company_facts"):
        if isinstance(result.get(key), dict):
            out[key] = result[key]
    if isinstance(result.get("document_summary"), dict):
        out.pop("document_summary_pending", None)
    artifacts = []
    if result.get("draft_id"):
        artifacts.append({"type": "draft", "id": result["draft_id"],
                          "version": result.get("version")})
    if result.get("grid_id"):
        artifacts.append({"type": "review_table", "id": result["grid_id"]})
    out["artifacts"] = artifacts
    return out


def _turn_response(message: dict) -> dict:
    metadata = message.get("metadata") or {}
    out = {"conversation_id": message["conversation_id"],
           "message_id": message["message_id"], "task": message.get("task"),
           "run_id": message.get("run_id"), "envelope": message.get("envelope"),
           "classification": metadata.get("classification") or {},
           "metadata": metadata, "files": metadata.get("files") or []}
    if metadata.get("sources"):
        out["sources"] = metadata["sources"]
    if metadata.get("document_evidence"):
        out["document_evidence"] = metadata["document_evidence"]
    if metadata.get("document_summary"):
        out["document_summary"] = metadata["document_summary"]
    if metadata.get("company_facts"):
        out["company_facts"] = metadata["company_facts"]
    if metadata.get("document_summary_pending"):
        out["note"] = "Preparing a structured summary from the selected documents."
    for artifact in metadata.get("artifacts") or []:
        if artifact.get("type") == "draft":
            out.update(draft_id=artifact["id"], version=artifact.get("version"))
        elif artifact.get("type") == "review_table":
            out["grid_id"] = artifact["id"]
    return out


CONVERSATION_UNAVAILABLE = "This conversation is unavailable."


# Words a follow-up leans on rather than names: cues, pronouns and question scaffolding.
_FOLLOW_UP_FILLER = frozenset(
    "and also what about how does do did is are was were can could would should will that this "
    "it its they them those these there then so if when which who whom whose why where the a an "
    "of to in on for at by with from be been being has have had not any some please explain "
    "expand summarise summarize tell me more happens happen".split())


def _names_own_subject(text: str) -> bool:
    """A follow-up that names its own subject ("And what happens if that quorum is not present
    at the meeting?") is researched on its own words. Only one that leans on the previous answer
    for its subject ("Does that apply to it?") is asked to name it: prior assistant answers are
    never evidence, so they are never used to fill the gap.
    """
    words = [w for w in re.findall(r"[a-z]+", text.casefold()) if len(w) > 2 and w not in _FOLLOW_UP_FILLER]
    return len(set(words)) >= 2


# A follow-up that continues the last question rather than starting a new one.
_CONTINUES = re.compile(r"^\s*(?:and|also|what about|how about)\b", re.I)


def _research_text(text: str, store, cid: str) -> str:
    """The words a continuing follow-up is researched on: the user's own previous question
    plus this one. "And for a private company?" after "What is the minimum number of directors
    for a public company?" is about directors; researched alone it was answered about share
    capital (live, 2026-11-12). Only the USER's words are carried -- an assistant answer is
    never evidence, so it never enters the query.
    """
    if not _CONTINUES.match(text):
        return text
    users = [m for m in (store.read_messages(cid) or []) if m.get("role") == "user"]
    previous = users[-1].get("text") if users else None
    if not isinstance(previous, str) or not previous.strip():
        return text
    return f"{previous.strip()} {text.strip()}"


def _conversation_send(args: dict, ctx: Context) -> dict:
    """Validate, reserve one idempotent message pair, then dispatch bounded work."""
    import hashlib
    import json
    import os
    import uuid
    from datetime import date
    from agents import intake
    from gateway import envelope as ev
    from gateway.store import StoreError, TurnConflict
    from gateway.jobs import QueueFull, INTERACTIVE

    text = args.get("text") or ""
    if not isinstance(text, str) or len(text) > MAX_CONVERSATION_CHARS:
        return _refuse("BAD_REQUEST", f"text must be a string of at most {MAX_CONVERSATION_CHARS} characters")
    raw_ids = args.get("file_ids") or []
    if (not isinstance(raw_ids, list) or len(raw_ids) > MAX_CONVERSATION_FILES
            or not all(isinstance(f, str) and 0 < len(f) <= 128 for f in raw_ids)):
        return _refuse("BAD_REQUEST", "file_ids must contain at most 20 document IDs")
    raw_ids = list(dict.fromkeys(raw_ids))
    if not text.strip() and not raw_ids:
        return _refuse("BAD_REQUEST", "text or at least one file_id is required")
    for name in ("conversation_id", "request_id", "matter_id", "as_of", "task_override"):
        if args.get(name) is not None and not isinstance(args[name], str):
            return _refuse("BAD_REQUEST", f"{name} must be a string")
    request_id = (args.get("request_id") or "").strip() or str(uuid.uuid4())
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", request_id):
        return _refuse("BAD_REQUEST", "request_id must be 8–128 letters, digits, hyphens or underscores")
    as_of = (args.get("as_of") or "").strip() or _today(ctx)
    try:
        date.fromisoformat(as_of)
    except ValueError:
        return _refuse("BAD_REQUEST", "as_of must be a valid YYYY-MM-DD date")
    sources = args.get("sources")
    if sources is not None and (not isinstance(sources, list) or len(sources) > 30
            or not all(isinstance(x, str) and 0 < len(x) <= 128 for x in sources)):
        return _refuse("BAD_REQUEST", "sources must be a list of source IDs")
    override = (args.get("task_override") or "").strip() or None
    if override is not None and override not in intake.TASKS:
        return _refuse("BAD_REQUEST", f"{override!r} is not a supported task")
    if ctx.store is None:
        return _refuse("NO_STORE", "A conversation needs a durable store.")
    store = ctx.store
    payload = {k: v for k, v in args.items() if k != "request_id" and v is not None}
    payload.update(text=text, file_ids=raw_ids, actor=ctx.actor)
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    try:
        prior = store.find_turn(request_id, digest)
        if prior is not None:
            return _turn_response(_reconcile_message(prior, ctx))
    except TurnConflict:
        return _refuse("IDEMPOTENCY_CONFLICT", "This request ID already belongs to different input.")

    _past, refusal = _law_date(as_of, ctx)
    if refusal:
        return refusal

    cid = (args.get("conversation_id") or "").strip() or str(uuid.uuid4())
    conv = store.read_conversation(cid)
    matter = (args.get("matter_id") or "").strip() or None
    if conv is not None and not access.row_allowed(ctx, conv):
        # 028. Another person's conversation reads exactly like no conversation.
        return _refuse("NOT_FOUND", CONVERSATION_UNAVAILABLE)
    if conv is not None:
        if "matter_id" in args and matter != conv.get("matter_id"):
            return _refuse("MATTER_CONFLICT", "A conversation stays in its original matter. Start a new conversation to change it.")
        matter = conv.get("matter_id")
        if matter is None and not access.row_allowed(ctx, conv, access.WRITE):
            return _refuse("NOT_FOUND", CONVERSATION_UNAVAILABLE)
    if matter is not None:
        refusal = access.require_matter(ctx, matter, access.WRITE)
        if refusal:
            return refusal
    from dataclasses import replace as _replace
    ctx = _replace(ctx, matter_id=matter)
    from gateway import document_evidence as de
    if override:
        task, classification = override, {"task": override, "decided_by": "override",
                                          "reason": "the caller named the task"}
    else:
        named = []
        for fid in raw_ids:
            row = store.read_vault_document(fid)
            if row is not None and not access.document_allowed(ctx, row):
                row = None
            legacy = ctx.documents.get(fid) or {}
            if row is None and legacy.get("tenant", ctx.tenant) == ctx.tenant:
                row = legacy
            named.append({"name": (row or {}).get("name") or "Unavailable document", "type": ""})
        got = intake.classify(text, files=named, facts=args.get("facts"))
        task, classification = got.task, got.to_dict()
    # An overview is a fallback for an otherwise undecided document question, never
    # permission to replace an explicit table, review, drafting or event workflow.
    if (raw_ids and not override and de.is_overview(text)
            and task in (intake.NEEDS_CLARIFICATION, intake.RESEARCH_QUESTION)):
        task = "RESEARCH_QUESTION"
        classification = {"task": task, "decided_by": "rules", "reason": "selected-document excerpt overview"}
    document_research = bool(raw_ids and task == "RESEARCH_QUESTION")
    document_summary = bool(document_research and de.is_overview(text))
    document_sources_enabled = sources is None or "vault" in sources
    resolved, refusal = documents._resolve_conversation_documents(raw_ids, ctx, matter,
        evidence_only=document_research, enabled=document_sources_enabled)
    if refusal:
        return refusal
    ctx = resolved
    files = _files_block(raw_ids, ctx)
    if document_summary and not document_sources_enabled:
        document_summary = False
    if document_summary and ctx.queue is None:
        return _refuse("QUEUE_UNAVAILABLE",
                       "Document summaries need the background worker. This request was not saved; retry when the worker is available.")
    if document_summary:
        try:
            from gateway import document_summary as ds
            ds.prepare(ctx.documents)
        except ds.SummaryError as error:
            return _refuse(error.code, error.detail)
        sha256_by_id = {}
        for fid in raw_ids:
            row = ctx.store.read_vault_document(fid)
            if (not row or not access.document_allowed(ctx, row)
                    or row.get("state") not in READABLE_VAULT_STATES or row.get("deleted_at")):
                return _refuse("DOCUMENT_UNAVAILABLE", "Save each selected file to the vault and wait until it is ready before summarizing.")
            sha256_by_id[fid] = row.get("sha256")
        from gateway import document_evidence as de
        initial_document_evidence = de.collect(text, ctx.documents, enabled=True)
    else:
        initial_document_evidence = None

    if raw_ids and task in ("REVIEW_DOCUMENT", "REVIEW_CONTRACT") and (
            len(raw_ids) != 1 or any(f["state"] == ev.CANNOT_READ for f in files)):
        task = intake.NEEDS_CLARIFICATION
        classification = {"task": task, "decided_by": "rules", "reason": "document is unavailable or ambiguous",
            "question": "Select one readable document to review. An unavailable document cannot be replaced by the instruction text."}
    elif conv and not raw_ids and task == "RESEARCH_QUESTION" and re.match(
            r"^\s*(?:(?:and|also)\b|what about (?:that|this|it)\b|(?:can|does|is|would|should) (?:it|that|this)\b|(?:explain|expand|summari[sz]e) (?:it|that|this)\b)", text, re.I) \
            and not _names_own_subject(text):
        task = intake.NEEDS_CLARIFICATION
        classification = {"task": task, "decided_by": "rules", "reason": "ambiguous follow-up",
            "question": "Please name the provision, document or issue in this follow-up. Prior assistant answers are not treated as legal evidence."}
    research_text = (_research_text(text, store, cid)
                     if conv and not raw_ids and task == "RESEARCH_QUESTION" else text)
    if _past is not None and (task != "RESEARCH_QUESTION" or document_research):
        # Only a research question reads the Act as it stood on a date. Every other task
        # (reviews, drafts, document reading, clarification) reads today's law or no law, so
        # stamping it with a past date would be today's answer wearing an old one.
        return _refuse("AS_OF_UNSUPPORTED", AS_OF_TASK_ONLY)
    if (not document_research or document_summary) and TASK_INTENT.get(task) and ctx.queue is not None:
        try:
            limit = max(1, int(os.environ.get("PLACEDON_CONVERSATION_QUEUE_LIMIT", "100")))
        except ValueError:
            limit = 100
        if ctx.queue.depth() >= limit:
            return _refuse("BUSY", "The workspace is busy. Your question has not been submitted; retry shortly.")
    metadata = {"schema": "conversation_turn.v1", "request_id": request_id,
                "classification": classification, "artifacts": [], "files": files, "as_of": as_of,
                "accepted_at": _now(ctx),
                **({"document_summary_pending": True,
                    "document_evidence": initial_document_evidence} if document_summary else {})}
    queued = None
    if (not document_research or document_summary) and TASK_INTENT.get(task) and ctx.queue is not None:
        intent = "document_summary" if document_summary else TASK_INTENT[task]
        job_args = ({"file_ids": raw_ids, "matter_id": matter,
                     "sha256_by_id": sha256_by_id, "sources": sources}
                    if document_summary else _task_args(task, research_text, raw_ids, ctx, args))
        queued = {"run_id": str(uuid.uuid4()), "intent": intent,
                  "args": job_args, "lane": INTERACTIVE}
    reply_id = str(uuid.uuid4())
    try:
        message, created = store.reserve_turn(
            {"conversation_id": cid, "title": text.strip()[:60] or "Attachment", "matter_id": matter,
             "actor_id": ctx.actor},
            {"message_id": str(uuid.uuid4()), "role": "user", "text": text, "file_ids": raw_ids},
            {"message_id": reply_id, "role": "assistant", "text": "", "file_ids": [],
             "task": task, "envelope": None, "metadata": metadata,
             "run_id": queued["run_id"] if queued else None},
            request_id=request_id, payload_digest=digest, queue=ctx.queue, queued=queued)
    except QueueFull:
        return _refuse("BUSY", "The workspace is busy. Your question has not been submitted; retry shortly.")
    except TurnConflict:
        return _refuse("IDEMPOTENCY_CONFLICT", "The request or matter changed while this turn was submitted.")
    except StoreError:
        # 028. A conversation id that names a row this actor cannot see: the insert does
        # nothing and the row lock finds nothing. Same answer as any unavailable thread.
        return _refuse("NOT_FOUND", CONVERSATION_UNAVAILABLE)
    if not created:
        return _turn_response(_reconcile_message(message, ctx))
    if queued is not None:
        response = _turn_response(message)
        if document_summary:
            response["note"] = "Preparing a structured summary from the selected documents."
        response["files"] = [{k: v for k, v in dict(f, state=ev.READING).items()
                              if k not in ("reason", "pages")} if f["state"] == ev.READ else f
                             for f in files]
        return response
    try:
        return _dispatch_conversation(args, ctx, cid=cid, text=research_text, raw_ids=raw_ids,
            as_of=as_of, task=task, classification=classification, reply_id=reply_id,
            metadata=metadata, files=files)
    except Exception:  # The durable question must have an explicit, sanitized failed reply.
        env = ev.failed(task=task, as_of=as_of,
                        detail="This request could not finish. Your question is saved; retry as a new turn.")
        store.update_message(reply_id, task=task, run_id=None, envelope=env, metadata=metadata)
        return {"conversation_id": cid, "message_id": reply_id, "classification": classification,
                "envelope": env, "metadata": metadata}


def _previous_user_text(store, cid: str, reply_id: str) -> str | None:
    """The user question before the one `reply_id` answers; never an assistant message.

    Document excerpts read a follow-up ("And how long is that?") together with it
    (document_evidence.collect previous_query). One turn back only.
    """
    messages = store.read_messages(cid) or []
    reply = next((m for m in messages if m.get("message_id") == reply_id), None)
    if reply is None:
        return None
    users = [m for m in messages if m.get("role") == "user" and m.get("ordinal", 0) < reply.get("ordinal", 0)]
    if len(users) < 2:
        return None
    previous = users[-2].get("text")
    return previous if isinstance(previous, str) and previous.strip() else None


def _dispatch_conversation(args, ctx, *, cid, text, raw_ids, as_of, task, classification,
                           reply_id, metadata, files):
    from agents import intake
    from gateway import envelope as ev
    store = ctx.store
    if raw_ids and task == "RESEARCH_QUESTION":
        from gateway import document_evidence as de
        evidence = de.collect(text, ctx.documents,
                              enabled=args.get("sources") is None or "vault" in args["sources"],
                              previous_query=_previous_user_text(store, cid, reply_id))
        metadata = dict(metadata, document_evidence=evidence)
        env = ev.build(status=ev.PARTIAL, task=task, as_of=as_of,
            text_blocks=[{"text": de.description(evidence), "citation_ids": []}],
            bodies=[], citations=[], files=files)
        store.update_message(reply_id, task=task, run_id=None, envelope=env, metadata=metadata)
        return _turn_response({"conversation_id": cid, "message_id": reply_id, "task": task,
                               "envelope": env, "metadata": metadata})
    # 4a. nothing to run.
    if task == intake.NEEDS_CLARIFICATION:
        env = ev.build(status=ev.NEEDS_CLARIFICATION, task=task, as_of=as_of,
                       text_blocks=[{"text": classification.get("question")
                                     or "Could you say what you would like done?",
                                     "citation_ids": []}],
                       bodies=[], citations=[], files=files)

        store.update_message(reply_id, task=task, run_id=None, envelope=env, metadata=metadata)
        return {"conversation_id": cid, "message_id": reply_id,
                "classification": classification, "envelope": env, "metadata": metadata}

    verb_name = TASK_VERB.get(task, "")
    if not verb_name:
        env = ev.build(status=ev.ABSTAINED, task=task, as_of=as_of,
                       text_blocks=[{"text": (
                           f"This is a {task} question and this engine cannot answer one "
                           f"yet: the intent is declared in agents/plans.py and no verb "
                           f"serves it. Nothing was read, so nothing follows about any "
                           f"obligation."), "citation_ids": []}],
                       bodies=[], citations=[], files=files)

        store.update_message(reply_id, task=task, run_id=None, envelope=env, metadata=metadata)
        return {"conversation_id": cid, "message_id": reply_id,
                "classification": classification, "envelope": env, "metadata": metadata}

    # 4c. short enough to answer now.
    from gateway.verbs.registry import by_name
    verb = by_name()[verb_name]
    built = None
    prose_note = ""
    if task == "DRAFT":
        template, source, source_run = _draft_source(cid, ctx)
        if template:
            from checker import draft_templates
            prose = args.get("prose")
            if not isinstance(prose, list):
                # Nobody supplied sentences, so ask a model for them. Job 3c. Whatever
                # comes back goes through the SAME admit/drop rule as caller-supplied
                # prose -- there is no second path and no softer rule for our own model.
                prose, prose_note = _draft_prose(template, source, ctx)
            built = draft_templates.build(template, source, prose=prose)
    result = verb.run(_task_args(task, text, raw_ids, ctx, args, built=built), ctx)
    _persist_result(ctx, result)
    if _critic_enabled() and task != "RESEARCH_QUESTION" and "critic" not in result:
        # "All answer tasks" means the critic is CONSULTED for all of them. It can only
        # act where there are cited statutory sentences to act on, which today is the
        # research path; a contract review's findings are playbook comparisons, not claims
        # about law, and have no spans for it to check. Said out loud rather than left as
        # a silent gap, so nobody reads a clean reply as "the critic approved this".
        result = dict(result, critic_note=(
            f"CRITIC_ENABLED is on and the critic did not run for a {task} turn: it "
            f"reviews cited statutory sentences, and this task produces none."))
    if built is not None and result.get("status") != "REFUSED":
        result = dict(result, drafted_from=source_run, template=built.kind,
                      dropped_claims=[dict(d) for d in built.dropped],
                      prose_note=prose_note)
    env = _envelope_for(task, result, as_of=as_of, run_id=result.get("run_id"),
                        files=files, ctx=ctx, question=text)

    metadata = _turn_metadata(metadata, result)
    store.update_message(reply_id, task=task, run_id=result.get("run_id"), envelope=env, metadata=metadata)
    out = {"conversation_id": cid, "message_id": reply_id,
           "classification": classification, "run_id": result.get("run_id"),
           "envelope": env, "metadata": metadata}
    # The source picker's per-source report rides the conversation RESPONSE, a sibling of
    # the envelope -- never inside answer_envelope.v1, which is versioned and immutable. It
    # is retrieval metadata (which sources were searched / searched-empty / not-searched),
    # not part of the legal answer, and it matches the shape the `ask` verb already returns.
    if result.get("sources"):
        out["sources"] = result["sources"]
    if metadata.get("company_facts"):
        out["company_facts"] = metadata["company_facts"]
    # The refusal/failure code rides the RESPONSE, a sibling of the versioned envelope (which
    # has no field for it) -- so a client can tell NO_MODEL / NOTHING_TRACED / NO_EVIDENCE
    # apart machine-readably without re-deriving it from prose. Same shape as `sources`.
    if result.get("code"):
        out["code"] = result["code"]
    if task == "DRAFT" and result.get("draft_id"):
        out["draft_id"] = result["draft_id"]
        out["version"] = result.get("version")
        if built is not None:
            # A drop is a fact about this reply, so it travels as a field and not only as
            # a sentence a client may not render.
            out["drafted_from"] = source_run
            out["template"] = built.kind
            out["dropped_claims"] = [dict(d) for d in built.dropped]
            out["prose_note"] = prose_note
    if task == "REVIEW_TABLE" and result.get("grid_id"):
        out["grid_id"] = result["grid_id"]
    return out


def _task_args(task: str, text: str, file_ids, ctx: Context, args: dict,
               *, built=None) -> dict:
    """The arguments the target verb takes. One place, so a task cannot be dispatched with
    a field the verb does not declare."""
    doc = ""
    for fid in file_ids or ():
        d = ctx.documents.get(fid) or {}
        if d.get("text"):
            doc = str(d["text"])
            break
    if task == "RESEARCH_QUESTION":
        # Thread the picked sources through to `ask`, so a conversation turn honours the
        # @-sources chip. Omitted when absent so the verb applies its own default.
        picked = args.get("sources")
        past = (args.get("as_of") or "").strip()
        return {"question": text, **({"sources": picked} if picked else {}),
                **({"as_of": past} if past and past != _today(ctx) else {})}
    if task == "EVENT_ASSESS":
        return {"event": (args.get("event") or "commercial_contract"),
                "facts": args.get("facts") or {}}
    if task == "REVIEW_TABLE":
        # One column per question asked, and with nothing to go on there is exactly one:
        # the user's own words. Inventing a six-column diligence grid from a sentence
        # would be guessing at what they want and spending a run per guess.
        return {"name": (text.strip()[:60] or "Review table"),
                "document_ids": list(file_ids or ()),
                "columns": [{"name": "answer", "kind": "text",
                             "question": text.strip() or "What does this document say?"}]}
    if task == "DRAFT":
        if built is not None:
            # Built from a run that already happened, by `checker/draft_templates.py`:
            # every statement of law in it is a quote from that run's citations, and the
            # model's connecting prose is MODEL_SUGGESTION, which blocks approval.
            return {"title": built.title, "body": built.body,
                    "slots": [s.to_dict() for s in built.slots],
                    "citations": list(built.citations),
                    "kind": args.get("kind") or built.kind}
        # No prior run to draft from. The conversation's words become the TITLE, and the
        # body starts empty with an UNKNOWN slot: a draft this engine invented prose for
        # would be a MODEL_SUGGESTION document, and `provenance_slots` exists to stop that
        # reaching a filing. The user fills the slots through draft.revise.
        return {"title": (text.strip()[:80] or "Draft"),
                "body": "",
                "slots": [{"name": "body", "value": "", "type": "UNKNOWN",
                           "note": ("nothing has been drafted yet: this engine does not "
                                    "write legal prose unprompted, and an UNKNOWN slot "
                                    "blocks approval until a person fills it")}],
                # Not a guessed statutory type: see DRAFT_KIND_UNKNOWN.
                "kind": args.get("kind") or DRAFT_KIND_UNKNOWN}
    if task == "REVIEW_CONTRACT":
        return {"text": doc or text, "name": "conversation upload",
                "test_data": args.get("test_data", False)}
    return {"text": doc or text, "name": "conversation upload"}


def _conversation_list(args: dict, ctx: Context) -> dict:
    """The threads, newest first. Tenant-scoped by the store, not by this handler."""
    if ctx.store is None:
        return _refuse("NO_STORE", "no store is configured, so there are no conversations")
    limit = args.get("limit")
    limit = int(limit) if isinstance(limit, (int, float, str)) and str(limit).isdigit() else 50
    matter_id = (args.get("matter_id") or "").strip()
    if not matter_id:
        # 8b: no cross-matter listing. Refused here AND in the store -- the store because
        # it is the last place that can refuse, this one because the refusal a user sees
        # should name the field they left out rather than surface a StoreError.
        return _refuse("BAD_REQUEST",
                       "matter_id is required: conversations are listed one matter at a "
                       "time. There is no 'all matters' listing, because a list of every "
                       "client's work is the accident this rule exists to prevent")
    refusal = access.require_matter(ctx, matter_id)
    if refusal:
        return refusal
    return {"matter_id": matter_id,
            "conversations": ctx.store.list_conversations(matter_id=matter_id,
                                                          limit=min(limit, 200))}


def _with_progress(message: dict, ctx: Context) -> dict:
    """A pending turn, with its run's live progress when the worker has recorded any.

    Optional and display only (031, gateway/progress.py). Read through the caller's own
    store, so the runs row-level security decides who sees it, as for the run itself.
    """
    progress = ctx.store.read_run_progress(message["run_id"])
    return dict(message, progress=progress) if progress else message


def _reconcile_message(message: dict, ctx: Context) -> dict:
    if message.get("role") != "assistant" or message.get("envelope") is not None:
        return message
    if not message.get("run_id"):
        from datetime import datetime
        metadata = message.get("metadata") or {}
        try:
            age = (datetime.fromisoformat(_now(ctx).replace("Z", "+00:00")) -
                   datetime.fromisoformat(metadata["accepted_at"].replace("Z", "+00:00"))).total_seconds()
        except (KeyError, ValueError, TypeError):
            return message
        if age < 300:
            return message
        from gateway import envelope as ev
        env = ev.failed(task=message["task"], as_of=metadata.get("as_of") or _today(ctx),
                        detail="This request was interrupted. Your question is saved. Check existing drafts before retrying as a new turn.")
        if ctx.store.expire_pending_message(message["message_id"], env):
            return dict(message, envelope=env)
        # The original request completed after the snapshot above. Never overwrite it.
        return next((m for m in ctx.store.read_messages(message["conversation_id"])
                     if m["message_id"] == message["message_id"]), message)
    # A worker stores its result BEFORE marking its job terminal. Check the job first,
    # then read the result; reversing these reads can freeze a stale failed attempt after
    # a retry has completed successfully between the two reads.
    if ctx.queue is not None:
        job = ctx.queue.get(message["run_id"])
        if job is not None and job.status in ("QUEUED", "LEASED"):
            return _with_progress(message, ctx)
    run = ctx.store.read(message["run_id"])
    if not run or run.get("status") in ("PLANNED", "RUNNING"):
        return _with_progress(message, ctx)
    metadata = message.get("metadata") or {"schema": "conversation_turn.v1", "artifacts": [], "files": []}
    result = dict(run.get("result") or {})
    if run.get("status") == "FAILED":
        result = {"status": "FAILED", "error": "The request could not finish. Your question is saved."}
    elif run.get("status") == "REFUSED" and not result.get("status"):
        result.update(status="REFUSED", detail="The request was cancelled or declined.")
    metadata = _turn_metadata(metadata, result)
    messages = ctx.store.read_messages(message["conversation_id"])
    question = next((m.get("text") or "" for m in messages
                     if m["ordinal"] == message["ordinal"] - 1 and m["role"] == "user"), "")
    env = _envelope_for(message["task"], result, as_of=metadata.get("as_of") or _today(ctx),
                        run_id=message["run_id"], files=metadata.get("files") or [],
                        ctx=ctx, question=question)
    ctx.store.update_message(message["message_id"], task=message["task"],
                             run_id=message["run_id"], envelope=env, metadata=metadata)
    return dict(message, envelope=env, metadata=metadata)


def _conversation_get(args: dict, ctx: Context) -> dict:
    """One thread and every message in it, in order, each with its stored envelope."""
    if ctx.store is None:
        return _refuse("NO_STORE", "no store is configured")
    cid = (args.get("conversation_id") or "").strip()
    if not cid:
        return _refuse("BAD_REQUEST", "conversation_id is required")
    conv = ctx.store.read_conversation(cid)
    if conv is None or not access.row_allowed(ctx, conv):
        return _refuse("NOT_FOUND", f"no conversation {cid!r} for this tenant")
    return {"conversation": conv, "messages": [
        _reconcile_message(message, ctx) for message in ctx.store.read_messages(cid)]}
