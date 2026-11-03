"""The vault (V1): upload, ingest, list, find, verify, delete, retry, summarize/research/compile."""
from __future__ import annotations

import re

from gateway import access
from gateway.store import READABLE_VAULT_STATES
from gateway.verbs.core import Context, _now, _refuse


# ── V1: the vault ────────────────────────────────────────────────────────────
#
# Every READ verb here is `mcp=False`, and that is a judgement rather than a limitation: a
# vault is the client's documents themselves, and there is no agent task that should be
# able to search one by default. `matters.list` opts out for the same kind of reason.


def _vault_ready(ctx: Context):
    if ctx.store is None:
        return _refuse("NO_STORE", "a vault is durable; it needs a store")
    if ctx.files is None:
        return _refuse("NO_VAULT",
                       "no file store is configured on this deployment, so there is "
                       "nowhere to put the bytes. Refused by name rather than accepting "
                       "an upload and writing it nowhere")
    return None


def _vault_upload(args: dict, ctx: Context) -> dict:
    """Store the bytes and queue one ingest job. A WRITE verb."""
    import logging
    import uuid
    refusal = _vault_ready(ctx)
    if refusal:
        return refusal
    name = (args.get("name") or "").strip()
    text = args.get("text")
    if not name:
        return _refuse("BAD_REQUEST", "a vault document needs a name")
    if not isinstance(text, str) or not text.strip():
        return _refuse("BAD_REQUEST",
                       "text is required. Binary upload is a route, not a verb -- see "
                       "the download routes in gateway/app.py for the shape it will take")
    matter = args.get("matter_id")
    if matter is not None and not isinstance(matter, str):
        return _refuse("BAD_REQUEST", "matter_id must be a string")
    matter = (matter or "").strip() or None
    if matter is not None:
        refusal = access.require_matter(ctx, matter, access.WRITE)
        if refusal:
            return refusal
    data = text.encode("utf-8")
    from checker import archive_guard as ag
    verdict = ag.inspect(data)
    if not verdict.ok:
        return _refuse("ARCHIVE_REFUSED", verdict.reason)
    try:
        sha = ctx.files.put(data)
    except Exception as exc:                                     # noqa: BLE001
        # A failed backing-store write is operational, not bad user input. Do not return
        # SDK exception text: it may carry account/container/request details. The HTTP
        # layer maps this stable code to 503 with Retry-After.
        from gateway.filestore import FileStoreUnavailable
        retryable = not isinstance(exc, FileStoreUnavailable) or exc.retryable
        logging.getLogger("gateway.verbs").warning(
            "vault_blob_write_failed", extra={"exception_type": type(exc).__name__,
                                               "retryable": retryable})
        return _refuse(
            "STORAGE_UNAVAILABLE" if retryable else "STORAGE_MISCONFIGURED",
            "Vault storage is temporarily unavailable; retry shortly." if retryable
            else "Vault storage is not configured for this operation. Contact your administrator.",
        )
    did = str(uuid.uuid4())
    doc = {"document_id": did, "matter_id": matter, "uploaded_by": ctx.actor,
           "sha256": sha, "name": name, "byte_count": len(data), "state": "PENDING"}
    atomic = {}
    if ctx.queue is not None:
        from agents.vault_ingest import INTENT
        from gateway.jobs import BULK as _LANE_BULK
        # The document, its run (`jobs.run_id` references `runs`) and its ingest job are ONE
        # unit. Written separately, a full queue or a crash between the writes left a
        # PENDING document that no worker would ever read. A1: vault ingest goes on BULK,
        # so it never takes a slot reserved for someone waiting.
        atomic = {"run": {"id": did, "intent": INTENT, "status": "PLANNED",
                          "actor_id": ctx.actor, "matter_id": matter, "refusal_code": None,
                          "steps": [], "propositions": []},
                  "queue": ctx.queue,
                  "queued": {"run_id": did, "intent": INTENT, "lane": _LANE_BULK,
                             "args": {"document_id": did, "sha256": sha, "name": name,
                                      "matter_id": args.get("matter_id")}}}
    try:
        registered = ctx.store.write_vault_document(doc, **atomic)
    except Exception as exc:                                     # noqa: BLE001
        from gateway.jobs import QueueFull
        from gateway.store import DuplicateVaultDocument
        if isinstance(exc, QueueFull):
            return _refuse("BUSY", "The work queue is full, so the document was not "
                                   "registered. Retry shortly.")
        if isinstance(exc, DuplicateVaultDocument):
            # The same bytes twice is one document, so attaching a file the vault already
            # holds hands back THAT document -- a refusal here left the composer saying
            # "Upload interrupted, try again", and trying again could never succeed.
            # A DELETED holder is not handed back: its text is gone and nothing can read it.
            existing = (ctx.store.read_vault_document(exc.document_id)
                        if exc.document_id else None)
            if (existing and existing.get("state") == "FAILED"
                    and access.document_allowed(ctx, existing, access.WRITE)):
                # These bytes were just stored again, so a failure caused by missing bytes
                # is repaired too. Same guards as vault.retry: no double processing.
                refusal = _requeue_failed(existing, ctx)
                if refusal:
                    return refusal
                return {"document_id": existing["document_id"], "sha256": sha,
                        "name": existing.get("name") or name, "state": "PENDING",
                        "job_id": None, "queue_error": None, "duplicate": True,
                        "retried": True,
                        "note": (f"'{existing.get('name') or name}' had failed to process; "
                                 f"these bytes are queued to be read again. Nothing new was "
                                 f"stored.")}
            if (existing and existing.get("state") != "DELETED"
                    and access.document_allowed(ctx, existing)):
                return {"document_id": existing["document_id"], "sha256": sha,
                        "name": existing.get("name") or name,
                        "state": existing.get("state") or "PENDING", "job_id": None,
                        "queue_error": None, "duplicate": True,
                        # 028: duplicates are per matter (filed) or per uploader
                        # (unfiled), never across people outside a shared matter.
                        "note": ((f"This matter already holds these bytes as "
                                  if existing.get("matter_id") else
                                  f"You already uploaded these bytes as ")
                                 + f"'{existing.get('name') or name}'; that document is "
                                 f"returned and nothing new was stored or queued.")}
            if existing and existing.get("state") == "DELETED":
                return _refuse("CONFLICT", (
                    f"These bytes were uploaded before as '{existing.get('name') or name}' "
                    f"and that document was deleted. A deleted document cannot be replaced "
                    f"by uploading identical bytes again; nothing was stored."))
            return _refuse("CONFLICT", "These bytes are already stored here and cannot be "
                                       "returned to you; nothing was stored.")
        # Bytes may now exist in Blob without a metadata row. Keep the response generic;
        # operators can use the exception class and database telemetry to diagnose it.
        logging.getLogger("gateway.verbs").error(
            "vault_registration_failed", extra={"exception_type": type(exc).__name__})
        return _refuse(
            "STORAGE_UNAVAILABLE",
            "The file could not be registered in the vault, and nothing was registered. "
            "Retry shortly.",
        )
    if atomic:
        queued = (registered or {}).get("job_id")
        note = ("stored and queued for ingestion. PENDING is not INGESTED: nothing "
                "is searchable until a worker has read it.")
    else:
        queued = None
        note = ("stored. No queue is configured, so nothing will ingest it and it "
                "will stay PENDING -- said plainly rather than left to look done.")
    return {"document_id": did, "sha256": sha, "name": name, "state": "PENDING", "job_id": queued,
            "queue_error": None, "note": note}


def _vault_ingest_job(args: dict, ctx: Context) -> dict:
    """Run one queued ingest. Verb-shaped, so `queue_handlers` can wrap it like the rest.

    `agents/vault_ingest.ingest` takes `files`, `store` and an `extract` callable rather
    than a Context, because it is an agent and agents are injected. This adapts the two
    shapes in ONE place: a worker that built the arguments itself would be a second
    definition of what ingestion needs.

    The extractor decodes UTF-8, because `vault.upload` takes TEXT -- its own refusal says
    binary upload is a route and not a verb. When that route exists this is where the
    page-by-page path (`checker/page_stream`) is wired in, and a document whose page fails
    becomes PARTIAL rather than silently short of a page.
    """
    refusal = _vault_ready(ctx)
    if refusal:
        return refusal
    from agents.vault_ingest import ingest
    from gateway.document_evidence import PAGE_BREAK

    def pages(data, name):
        # A PDF's pages arrive joined by form feeds. A page with no text layer is NAMED,
        # so the document is PARTIAL rather than silently short of a page.
        from checker.page_stream import PARTIAL, Extraction
        texts = data.decode("utf-8", "replace").split(PAGE_BREAK)
        failed = tuple(n for n, t in enumerate(texts, 1) if not t.strip())
        return Extraction(status=PARTIAL if failed else "COMPLETE", page_count=len(texts),
                          pages={n: t for n, t in enumerate(texts, 1) if t.strip()},
                          failed_pages=failed)

    # The job's args name a document; everything else comes from that document's row, read
    # under this job actor's RLS. Never the args' sha256 (the file store would serve any
    # file by hash), matter_id (it would refile the row) or a deleted document.
    did = str(args.get("document_id") or "")
    row = ctx.store.read_vault_document(did) if did else None
    if (row is None or row.get("deleted_at") or row.get("state") == "DELETED"
            or not access.document_allowed(ctx, row, access.WRITE)):
        return _refuse("NOT_FOUND", "This document is unavailable to you; nothing was read.")
    args = {"document_id": row["document_id"], "sha256": row["sha256"],
            "name": row.get("name") or "", "matter_id": row.get("matter_id")}
    paged = PAGE_BREAK.encode() in (ctx.files.get(args["sha256"]) or b"")
    outcome = ingest(args, files=ctx.files, store=ctx.store,
                     extract=lambda data, name: data.decode("utf-8", "replace"),
                     pages=pages if paged else None)
    return outcome.to_dict()


def _vault_list(args: dict, ctx: Context) -> dict:
    """Browse only metadata in one matter or the unfiled workspace scope."""
    import uuid
    if ctx.store is None:
        return _refuse("NO_STORE", "Document storage is not configured.")
    matter = args.get("matter_id")
    if matter is not None:
        if not isinstance(matter, str):
            return _refuse("BAD_REQUEST", "Choose a valid matter.")
        try:
            matter = str(uuid.UUID(matter))
        except ValueError:
            return _refuse("BAD_REQUEST", "Choose a valid matter.")
        refusal = access.require_matter(ctx, matter)
        if refusal:
            return refusal
    query = args.get("query", "")
    if not isinstance(query, str) or len(query) > 120:
        return _refuse("BAD_REQUEST", "Search names with at most 120 characters.")
    def number(key, default, low, high):
        raw = args.get(key, default)
        if isinstance(raw, bool) or not re.fullmatch(r"[0-9]{1,5}", str(raw)):
            raise ValueError(key)
        value = int(raw)
        if not low <= value <= high:
            raise ValueError(key)
        return value
    try:
        limit = number("limit", 30, 1, 50)
        offset = number("offset", 0, 0, 10000)
    except ValueError:
        return _refuse("BAD_REQUEST", "Use a page size of 1–50 and an offset of 0–10000.")
    rows = ctx.store.browse_vault_documents(matter_id=matter, query=query.strip(),
                                          limit=limit + 1, offset=offset)
    if matter is None:
        # 028. Unfiled means YOURS, plus anything shared firm-wide. Postgres already
        # filters this; memory has no policy, and the check is the same sentence here.
        rows = access.readable_documents(ctx, rows)
    _catalog = ("document_id", "sha256", "name", "state", "matter_id", "byte_count", "doc_class")
    rows = [{k: r.get(k) for k in _catalog} for r in rows]
    more = len(rows) > limit
    next_offset = offset + limit if more and offset + limit <= 10000 else None
    return {"documents": rows[:limit], "next_offset": next_offset,
            "truncated": more and next_offset is None,
            "scope": "matter" if matter else "unfiled", "matter_id": matter,
            "note": "Documents in this matter." if matter else
                    "Your unfiled documents, and any shared with the firm. Files in "
                    "matters are listed per matter."}


def _vault_status(args: dict, ctx: Context) -> dict:
    """One document, or the whole vault's counts. Read-only, off MCP."""
    if ctx.store is None:
        return _refuse("NO_STORE", "no store is configured")
    did = (args.get("document_id") or "").strip()
    if did:
        row = ctx.store.read_vault_document(did)
        if row is None or not access.document_allowed(ctx, row):
            return _refuse("NOT_FOUND", f"no vault document {did!r} for this tenant")
        return dict(row, tags=ctx.store.read_vault_tags(did))
    counts = ctx.store.vault_counts()
    return dict(counts, note=(
        f"{counts['documents']} document(s). {counts['unsearchable']} cannot be searched "
        f"-- they are PENDING, CANNOT_READ or FAILED, and a search answers from the rest. "
        f"{counts['deleted']} have been deleted; their rows remain and their bytes do "
        f"not."))


def _vault_index(ctx: Context):
    from checker.vault_search import Index
    counts = ctx.store.vault_counts()
    # 028. Only what this actor may read: its matters' documents, its own unfiled ones and
    # any shared firm-wide. The search was firm-wide, which under per-matter access is a
    # search across clients the searcher does not act for.
    return Index.build(access.readable_documents(ctx, ctx.store.read_vault_chunks()),
                       tenant_id=str(ctx.tenant),
                       unsearchable=int(counts.get("unsearchable") or 0))


def _vault_find(args: dict, ctx: Context) -> dict:
    """BM25 across this TENANT's vault. Read-only, off MCP."""
    if ctx.store is None:
        return _refuse("NO_STORE", "no store is configured")
    query = (args.get("query") or "").strip()
    if not query:
        return _refuse("BAD_REQUEST", "a query is required")
    try:
        limit = int(args.get("limit") or 10)
    except (TypeError, ValueError):
        return _refuse("BAD_REQUEST", "limit must be a whole number")
    res = _vault_index(ctx).search(query, limit=max(1, min(limit, 50))).to_dict()
    res["scope"] = "accessible"
    res["scope_note"] = ("searched every document you can read: the matters you are a "
                         "member of, your unfiled documents, and any shared with the firm. "
                         "Matters you are not a member of are not searched")
    return res


# The checks `vault.verify` runs, in order. Named because they FAIL differently and the
# remedies differ: a deleted document is intended, a missing object is a file store that
# lost something, and a hash mismatch is bytes that changed under us. One boolean over the
# three makes "the bytes are gone" and "the bytes changed" the same answer.
VERIFY_NOT_DELETED = "the document is not deleted"
VERIFY_BYTES_PRESENT = "the file store holds its bytes"
VERIFY_HASH_MATCHES = "the bytes hash to the key they are stored under"
VERIFY_PASS, VERIFY_FAIL, VERIFY_NOT_RUN = "PASS", "FAIL", "NOT RUN"


def _vault_verify(args: dict, ctx: Context) -> dict:
    """Do the stored bytes still hash to the key they were stored under? Read-only.

    Returns a line PER CHECK. It used to return one `verified` boolean with a `detail`
    string, and the three branches that produced it were already three different findings
    -- deleted, absent, mismatched -- flattened into true/false on the way out. A caller
    could not tell them apart without parsing English, and a UI showing one real/fake badge
    was the shape that boolean invited.

    `verified` is kept, as the AND of the checks, so an existing caller is not broken.
    """
    refusal = _vault_ready(ctx)
    if refusal:
        return refusal
    did = (args.get("document_id") or "").strip()
    row = ctx.store.read_vault_document(did) if did else None
    if row is None or not access.document_allowed(ctx, row):
        return _refuse("NOT_FOUND", f"no vault document {did!r} for this tenant")

    def answer(checks: list[dict], note: str) -> dict:
        return {"document_id": did, "checks": checks,
                "verified": all(c["result"] == VERIFY_PASS for c in checks),
                # The one-line summary, kept for a caller that only wants a sentence.
                "detail": note, "note": note}

    if row.get("deleted_at"):
        return answer(
            [{"name": VERIFY_NOT_DELETED, "result": VERIFY_FAIL,
              "detail": "deleted on " + str(row.get("deleted_at"))},
             {"name": VERIFY_BYTES_PRESENT, "result": VERIFY_NOT_RUN,
              "detail": "not run: this workspace no longer has access to the deleted document"},
             {"name": VERIFY_HASH_MATCHES, "result": VERIFY_NOT_RUN,
              "detail": "not run: access to this deleted document is revoked"}],
            "this document was deleted from this workspace. Shared bytes may remain under retention policy")

    not_deleted = {"name": VERIFY_NOT_DELETED, "result": VERIFY_PASS,
                   "detail": "the record is live"}
    try:
        data = ctx.files.get(row["sha256"])
    except Exception as e:                                       # noqa: BLE001
        return answer(
            [not_deleted,
             {"name": VERIFY_BYTES_PRESENT, "result": VERIFY_FAIL,
              "detail": f"{type(e).__name__}: {str(e)[:160]}"},
             {"name": VERIFY_HASH_MATCHES, "result": VERIFY_NOT_RUN,
              "detail": "not run: the bytes could not be read"}],
            f"the file store could not return the bytes: {type(e).__name__}")
    if data is None:
        return answer(
            [not_deleted,
             {"name": VERIFY_BYTES_PRESENT, "result": VERIFY_FAIL,
              "detail": "the file store has no object under this key"},
             {"name": VERIFY_HASH_MATCHES, "result": VERIFY_NOT_RUN,
              "detail": "not run: there were no bytes to hash"}],
            "the row names bytes the file store does not hold")

    # `files.get` is keyed BY the hash and verifies it on read, so reaching here is the
    # hash check passing. Stated rather than assumed, because a reader of this list is
    # entitled to know which code actually did the comparing.
    return answer(
        [not_deleted,
         {"name": VERIFY_BYTES_PRESENT, "result": VERIFY_PASS,
          "detail": f"the file store returned {len(data)} bytes"},
         {"name": VERIFY_HASH_MATCHES, "result": VERIFY_PASS,
          "detail": "the file store is keyed by the hash and checks it on read"}],
        f"re-read {len(data)} bytes and they hash to the key they were stored under")


def _vault_summarize(args: dict, ctx: Context) -> dict:
    """What is KNOWN about one document. Not a model summary, and it says so."""
    if ctx.store is None:
        return _refuse("NO_STORE", "no store is configured")
    did = (args.get("document_id") or "").strip()
    row = ctx.store.read_vault_document(did) if did else None
    if row is None or not access.document_allowed(ctx, row):
        return _refuse("NOT_FOUND", f"no vault document {did!r} for this tenant")
    tags = ctx.store.read_vault_tags(did)
    chunks = [c for c in ctx.store.read_vault_chunks() if c["document_id"] == did]
    return {"document_id": did, "name": row.get("name"),
            "doc_class": row.get("doc_class"), "class_reason": row.get("class_reason"),
            "state": row.get("state"), "text_chars": row.get("text_chars"),
            "chunks": len(chunks), "tags": tags,
            "note": ("This is what is RECORDED about the document -- its class, the "
                     "clauses found and the sentence each was found in. It is not a "
                     "written summary: no model has read this document, and a paragraph "
                     "of prose here would be the one thing in the vault nobody could "
                     "check against the file.")}


def _vault_research(args: dict, ctx: Context) -> dict:
    """Search the vault and return the PASSAGES. No prose, and it says why."""
    found = _vault_find(args, ctx)
    if found.get("status") == "REFUSED":
        return found
    hits = found.get("hits") or []
    return dict(found, passages=hits, answer=None, note=(
        f"{len(hits)} passage(s) from the firm's own documents, each with the document it "
        f"came from. No answer is written over them: a sentence synthesised from a "
        f"client's contracts is a statement about that client's position, and this engine "
        f"states nothing it cannot quote. Read the passages."))


def _vault_compile(args: dict, ctx: Context) -> dict:
    """One matter's documents, with their classes and clause tags. Read-only."""
    if ctx.store is None:
        return _refuse("NO_STORE", "no store is configured")
    matter_id = (args.get("matter_id") or "").strip()
    if not matter_id:
        return _refuse("BAD_REQUEST",
                       "matter_id is required: a bundle is compiled for one matter (8b)")
    refusal = access.require_matter(ctx, matter_id)
    if refusal:
        return refusal
    try:
        docs = ctx.store.list_vault_documents(matter_id=matter_id)
    except Exception as e:                                       # noqa: BLE001
        return _refuse("BAD_REQUEST", str(e)[:200])
    out = []
    for d in docs:
        out.append(dict(d, tags=ctx.store.read_vault_tags(d["document_id"])))
    unreadable = [d["name"] for d in docs if d.get("state") not in READABLE_VAULT_STATES]
    # 029. Read, but not whole: pages without a text layer are missing from these.
    incomplete = [d["name"] for d in docs if d.get("state") == "PARTIAL"]
    return {"matter_id": matter_id, "documents": out, "count": len(out),
            "not_ingested": unreadable, "incomplete": incomplete,
            "note": (f"{len(out)} document(s) filed to this matter. "
                     + (f"{len(unreadable)} could not be read and are listed by name, so "
                        f"a bundle is never quietly short: {unreadable[:5]}. "
                        if unreadable else "")
                     + (f"{len(incomplete)} were read except for pages with no text layer: "
                        f"{incomplete[:5]}." if incomplete else "")
                     + ("" if unreadable or incomplete else "Every one was read."))}


def _vault_delete(args: dict, ctx: Context) -> dict:
    """Revoke this tenant's document and chunks; defer shared-byte purge."""
    refusal = _vault_ready(ctx)
    if refusal:
        return refusal
    did = (args.get("document_id") or "").strip()
    row = ctx.store.read_vault_document(did) if did else None
    if row is None or not access.document_allowed(ctx, row):
        return _refuse("NOT_FOUND", f"no vault document {did!r} for this tenant")
    if not access.document_allowed(ctx, row, access.WRITE):
        return _refuse("FORBIDDEN", "You can read this document but not delete it.")
    if row.get("deleted_at"):
        return _refuse("ALREADY_DELETED",
                       f"{did} was already deleted on {row['deleted_at']}. Saying so is "
                       f"more useful than reporting a second destruction that did not "
                       f"happen")
    gone = ctx.store.delete_vault_document(did, now=_now(ctx))
    # The content-addressed byte store may be shared across tenants. A tenant-scoped
    # reference query cannot prove that no other tenant still needs the same SHA. Purge
    # belongs to a privileged retention job with a global reference check, not this verb.
    return {"document_id": did, "deleted": bool(gone), "bytes_destroyed": False,
            "note": "The document is deleted from this workspace and its searchable chunks are removed. Shared stored bytes are retained until a retention job can safely purge them."}



def _requeue_failed(row: dict, ctx: Context) -> dict | None:
    """Put a FAILED document back to PENDING with its job requeued. None on success.

    The one implementation behind `vault.retry` and a re-upload of the same bytes. The
    store's guard (`state = 'FAILED'`) and the queue's (`status = 'DEAD'`) are what stop a
    double retry from processing the document twice; this only maps their answers.
    """
    from gateway.jobs import QueueError, QueueFull
    from gateway.store import RetryConflict
    if ctx.queue is None:
        return _refuse("NO_QUEUE", "No work queue is configured, so nothing could read "
                                   "this document again.")
    if ctx.files.get(row["sha256"]) is None:
        return _refuse("BYTES_MISSING", "The stored file is missing, so retrying would fail "
                                        "the same way. Upload the file again.")
    try:
        moved = ctx.store.retry_vault_document(row["document_id"], queue=ctx.queue)
    except QueueFull:
        return _refuse("BUSY", "The work queue is full. Retry shortly; nothing was changed.")
    except (QueueError, RetryConflict):
        return _refuse("CONFLICT", "This document's processing job could not be requeued; "
                                   "nothing was changed.")
    if not moved:
        return _refuse("CONFLICT", "This document is no longer FAILED -- it may already "
                                   "have been retried. Nothing was changed.")
    return None


def _vault_retry(args: dict, ctx: Context) -> dict:
    """Read a FAILED document again. A WRITE verb; LAWYER, like vault.upload."""
    refusal = _vault_ready(ctx)
    if refusal:
        return refusal
    did = (args.get("document_id") or "").strip()
    row = ctx.store.read_vault_document(did) if did else None
    if row is None or not access.document_allowed(ctx, row):
        return _refuse("NOT_FOUND", f"no vault document {did!r} for this tenant")
    if not access.document_allowed(ctx, row, access.WRITE):
        return _refuse("FORBIDDEN", "You can read this document but not retry it.")
    if row.get("state") == "PENDING" and ctx.queue is not None:
        # The worker marks the document FAILED in a second step after its job goes DEAD. A
        # crash between the two leaves PENDING over a DEAD job; finish that step here, so
        # the document is not stuck with no way to retry it.
        job = ctx.queue.get(did)
        if job is not None and job.status == "DEAD":
            ctx.store.fail_vault_document(did, job.dead_reason or "processing stopped")
            row = ctx.store.read_vault_document(did) or row
    if row.get("state") != "FAILED":
        return _refuse("CONFLICT", f"Only a FAILED document can be retried; this one is "
                                   f"{row.get('state')}. Nothing was changed.")
    refusal = _requeue_failed(row, ctx)
    if refusal:
        return refusal
    return {"document_id": did, "name": row.get("name"), "state": "PENDING", "retried": True,
            "note": "Queued to be read again. PENDING is not INGESTED: nothing is searchable "
                    "until a worker has read it."}
