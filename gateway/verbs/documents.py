"""documents.upload, document summaries, document.verify and document.check."""
from __future__ import annotations

from gateway import access
from gateway.store import READABLE_VAULT_STATES
from gateway.verbs import model_access
from gateway.verbs.core import Context, _affirmed, _now, _partial_note, _refuse
from gateway.verbs.model_access import task_providers
from gateway.verbs.vault import _vault_ready


def _resolve_conversation_documents(file_ids, ctx: Context, matter_id, *, evidence_only=False, enabled=True):
    """Resolve selected vault IDs using tenant rows before touching the byte store.

    Legacy process-local uploads use the authenticated actor's cache view. Unknown
    or unreadable files remain explicit CANNOT_READ entries; no task receives the user's
    instruction as a substitute for a missing document.
    """
    import hashlib
    from dataclasses import replace
    from gateway.filestore import FileStoreError
    from gateway import document_evidence as de
    resolved = {}
    byte_total = 0
    for fid in file_ids:
        row = ctx.store.read_vault_document(fid)
        if row is not None and not access.document_allowed(ctx, row):
            row = None  # 028. Not yours reads as not there.
        if row is not None:
            if row.get("matter_id") != matter_id:
                return None, _refuse("DOCUMENT_SCOPE_MISMATCH",
                                     "The selected document belongs to a different matter.")
            doc = {"name": row["name"]}
            if evidence_only and not enabled:
                doc["cannot_read"] = "Document sources were not selected; no text was read."
            elif evidence_only and (row.get("byte_count", 0) > de.MAX_DOCUMENT_BYTES
                    or byte_total + row.get("byte_count", 0) > de.MAX_TOTAL_BYTES):
                doc.update(cannot_read="Document exceeds this turn's reading limit.", limit_exceeded=True)
            elif row.get("deleted_at") or row.get("state") not in READABLE_VAULT_STATES:
                doc["cannot_read"] = "This document is not ready to read. Check its upload status."
            elif ctx.files is None:
                doc["cannot_read"] = "The document file store is unavailable. Nothing was read."
            else:
                try:
                    data = ctx.files.get(row["sha256"])
                    if data is None or hashlib.sha256(data).hexdigest() != row["sha256"]:
                        raise ValueError("document hash mismatch")
                    byte_total += len(data)
                    if evidence_only and (len(data) > de.MAX_DOCUMENT_BYTES or byte_total > de.MAX_TOTAL_BYTES):
                        doc["limit_exceeded"] = True
                        raise ValueError("document exceeds reading limit")
                    doc["text"] = data.decode("utf-8")
                    if not doc["text"].strip():
                        raise ValueError("empty document")
                    doc["doc_class"], doc["class_reason"] = row.get("doc_class"), row.get("class_reason")
                    if row.get("state") == "PARTIAL":
                        # 029. Readable, and incomplete -- the reader is told which pages.
                        doc["partial"] = _partial_note(row.get("class_reason"))
                except (OSError, ValueError, UnicodeError, FileStoreError):
                    doc["cannot_read"] = "The saved document could not be read or verified."
            resolved[fid] = doc
        else:
            legacy = ctx.documents.get(fid)
            if evidence_only:
                resolved[fid] = {"name": "Unavailable document", "cannot_read":
                                 "Save this file to the vault before researching it; a durable source is required."}
            elif legacy and legacy.get("tenant", ctx.tenant) == ctx.tenant:
                resolved[fid] = dict(legacy)
                if not legacy.get("text") and not legacy.get("cannot_read"):
                    resolved[fid]["cannot_read"] = "The document text is unavailable; upload it again."
            else:
                resolved[fid] = {"name": "Unavailable document", "cannot_read":
                                 "This document is unavailable in this workspace. Nothing was read."}
    return replace(ctx, documents=resolved), None


SUMMARY_UNAVAILABLE_WHY = {
    "NO_PERMITTED_PROVIDER": "No document-summary model permitted for client documents is "
                             "configured (summaries may only use the India-region provider).",
    "PROVIDER_REFUSED_ACCESS": "The permitted model provider refused access for this "
                               "deployment's account.",
}


def _summary_unavailable(reason: str) -> dict:
    """A known configuration or access block: the summary cannot run until an operator acts,
    so it is not a retryable FAILED. Recorded on the turn's metadata (_turn_metadata), so a
    reopened conversation shows the same state. No other provider is tried: client
    documents may go only to the permitted one (PLAN_22 D3)."""
    return {"status": "REFUSED", "code": "SUMMARY_UNAVAILABLE",
            "document_summary_unavailable": {"reason": reason, "retryable": False},
            "detail": "Document summarization is unavailable. No summary was generated."}


def _summary_call_failure(error: Exception) -> dict:
    """The provider call raised: an access refusal is unavailable; anything else (throttling,
    timeouts, 5xx) is transient and stays a retryable FAILED."""
    from checker.bedrock_model import ProviderNotReady
    if isinstance(error, ProviderNotReady):
        return _summary_unavailable("PROVIDER_REFUSED_ACCESS")
    return {"status": "FAILED", "code": "SUMMARY_PROVIDER_FAILED",
            "error": "The document summary could not be completed. Your document remains unchanged."}


def _document_summary_job(args: dict, ctx: Context) -> dict:
    """One bounded summary attempt, reauthorizing and rereading selected vault files."""
    from gateway import document_summary as ds
    from checker import public_only, router

    file_ids = args.get("file_ids")
    matter_id = args.get("matter_id")
    expected = args.get("sha256_by_id")
    sources = args.get("sources")
    if (not isinstance(file_ids, list) or not 1 <= len(file_ids) <= ds.MAX_SUMMARY_DOCUMENTS
            or not all(isinstance(fid, str) for fid in file_ids)
            or len(set(file_ids)) != len(file_ids) or not isinstance(expected, dict)
            or set(expected) != set(file_ids)
            or (sources is not None and (not isinstance(sources, list)
                or not all(isinstance(source, str) for source in sources)
                or "vault" not in sources))
            or (matter_id is not None and not isinstance(matter_id, str))):
        return _refuse("BAD_REQUEST", "The queued document-summary request is incomplete or invalid.")
    if ctx.store is None or ctx.files is None:
        return _refuse("NO_STORE", "The document store is unavailable; no summary was generated.")
    # Every job, including direct runs.submit calls, repeats authorization at execution.
    for fid in file_ids:
        row = ctx.store.read_vault_document(fid)
        if (not row or not access.document_allowed(ctx, row)
                or row.get("deleted_at") or row.get("state") not in READABLE_VAULT_STATES
                or row.get("matter_id") != matter_id or row.get("sha256") != expected.get(fid)):
            return _refuse("DOCUMENT_SCOPE_MISMATCH", "A selected document changed or is unavailable. No summary was generated.")
    resolved, refusal = _resolve_conversation_documents(file_ids, ctx, matter_id,
                                                         evidence_only=True, enabled=True)
    if refusal:
        return refusal
    try:
        evidence = ds.prepare(resolved.documents)
        model_prompt = ds.prompt(evidence)
        text = "\n".join(p["text"] for p in evidence["passages"])
        origin = public_only.clear_matter(text, name="selected conversation documents",
                                          provider=router.BEDROCK)
    except ds.SummaryError as error:
        return _refuse(error.code, error.detail)
    except Exception:
        return _refuse("DOCUMENT_UNAVAILABLE", "The selected text could not be prepared safely.")
    served, refusal = model_access._served_or_refusal((origin,), name="document_summary",
        purpose=router.EXTRACTION, consequence=router.HIGH, ctx=ctx,
        timeout_seconds=25, retry_tries=1,
        allowed_providers=task_providers("document_summary"))
    if refusal:
        if refusal.get("code") == "NO_BUDGET":
            return refusal
        return _summary_unavailable("NO_PERMITTED_PROVIDER")
    try:
        raw = served.call(model_prompt)
    except Exception as error:
        # Provider adapters settle their reservation even when transport/usage is uncertain.
        ctx.last_steps.append({"capability": "document.summary", "status": "FAILED",
                               "provider": served.provider, "model": served.model,
                               "region": served.region, "error": type(error).__name__,
                               "cost_note": "Provider attempt failed; usage may be unknown and was accounted by its adapter."})
        return _summary_call_failure(error)
    try:
        summary = ds.parse(raw, evidence)
    except ds.SummaryError as error:
        try:
            step = served.step_fields()
            ctx.last_steps.append({"capability": "document.summary", "status": "FAILED", **step})
        except Exception:
            ctx.last_steps.append({"capability": "document.summary", "status": "FAILED",
                                   "provider": served.provider, "model": served.model,
                                   "region": served.region, "cost_note": "Provider usage could not be recorded in the run trace."})
        return {"status": "FAILED", "code": error.code, "error": error.detail}
    try:
        step = served.step_fields()
    except Exception:
        return {"status": "FAILED", "code": "SUMMARY_ACCOUNTING_FAILED",
                "error": "Summary accounting could not be confirmed. The result was withheld."}
    ctx.last_steps.append({"capability": "document.summary", "status": "ANSWERED", **step})
    result_status = "PARTIAL" if summary["status"] == "SUMMARY_DRAFT_READY" else "ABSTAINED"
    return {"status": result_status, "document_summary": summary,
            "summary_note": "This is a model-generated summary draft. Quotations show source locations; a lawyer must review meaning and completeness."}
# ── move 8 (T3): document.verify, one line per check ────────────────────────
# `checker/doc_verification.py` has done this work since before the gateway existed:
# `verify_document(path)` runs the PDF signature parse (`pdf_signature`), the ASN.1 decode
# (`asn1`), the chain walk against `checker/certs/` and the revocation check
# (`revocation`), and derives COMPLETE / INCOMPLETE / FAILED from the parts. None of it was
# reachable through a verb, so the product could not answer "is this document genuine?" at
# all.
#
# ONE LINE PER CHECK, like `vault.verify` (move 1). The reason is the same and it is worth
# repeating: a single genuine/fake badge is a summary that can disagree with the facts it
# summarises, and `Verification.overall_status` is a derived property for exactly that
# reason -- it was once a stored field and went stale.

# What each check is, in words a reader can act on. Keyed on the `Verification` field, so a
# field added to that dataclass and not described here fails the gate rather than appearing
# in a response as a bare identifier.
VERIFY_CHECK_NAMES = {
    "file_integrity": "the signed bytes have not changed since signing",
    "signature": "the digital signature validates against those bytes",
    "certificate_chain": "the signing certificate chains to a CCA India root",
    "certificate_validity_at_signing": "the certificate was valid on the day it signed",
    "revocation": "the certificate was not revoked at that time",
    "trusted_timestamp": "a trusted timestamp fixes when it was signed",
    "official_issuer_match": "the issuer matches the official record",
    "official_record_match": "the document matches the official record",
}

# The two checks that need a permission nobody has yet. NOT_CHECKED with this reason, never
# a pass and never a failure: "we did not look" and "we looked and it did not match" are
# different findings, and only the first is true today.
VERIFY_NEEDS_PERMISSION = ("official_issuer_match", "official_record_match")
VERIFY_PERMISSION_NOTE = (
    "NOT CHECKED: comparing a document against the official record needs an MCA/DigiLocker "
    "permission this deployment does not hold. This is not a pass and not a failure -- "
    "nothing was compared. docs/guides/INTEGRATIONS_CHECKLIST.md names what unlocks it"
)


def _document_verify(args: dict, ctx: Context) -> dict:
    """Signature, chain, revocation and coverage for one stored document. Read-only.

    Reads the bytes from the content-addressed file store and runs them through
    `checker/doc_verification.verify_document`. `offline=True` always: a revocation check
    that reached out would be an external network call, and standing rule 7 forbids one.
    An OCSP/CRL lookup nobody made is NOT_CHECKED, which the response says.
    """
    import os
    import tempfile
    from checker import doc_verification as dv

    refusal = _vault_ready(ctx)
    if refusal:
        return refusal
    did = (args.get("document_id") or "").strip()
    if not did:
        return _refuse("BAD_REQUEST", "document_id is required")
    row = ctx.store.read_vault_document(did)
    if row is None or not access.document_allowed(ctx, row):
        return _refuse("NOT_FOUND", f"no document {did!r} for this tenant")
    if row.get("deleted_at"):
        return _refuse("GONE",
                       f"document {did} was deleted on {row.get('deleted_at')}; its bytes "
                       f"are destroyed on purpose, so there is nothing to verify")
    try:
        data = ctx.files.get(row["sha256"])
    except Exception as e:                                       # noqa: BLE001
        data, why = None, f"{type(e).__name__}: {str(e)[:100]}"
    else:
        # `LocalFileStore.get` returns **None** for a key it does not hold rather than
        # raising, so the `except` above could never fire for the commonest case. Measured:
        # the None flowed into the parser and came back as VERIFY_FAILED -- "we could not
        # read this as a signed PDF" -- which blames the document for our missing file.
        why = "the file store holds no bytes under that key"
    if data is None:
        return _refuse("NOT_FOUND",
                       f"the record exists and its bytes are not in the file store "
                       f"({why}). Nothing was verified, and that is a failure of OURS -- "
                       f"it says nothing about the document")
    # `verify_document` takes a PATH, because every tool underneath it does. Written to a
    # temp file and removed in a `finally`: a client document left on disk after a read-only
    # verb is a data-residency problem, not an untidy directory.
    fd, tmp = tempfile.mkstemp(suffix=".pdf", prefix="placedon-verify-")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        v = dv.verify_document(tmp, offline=True)
    except Exception as e:                                       # noqa: BLE001
        return _refuse("VERIFY_FAILED",
                       f"the document could not be read as a signed PDF "
                       f"({type(e).__name__}: {str(e)[:120]}). A document we cannot parse "
                       f"is not a document we have found fault with")
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass

    checks = []
    for field, sentence in VERIFY_CHECK_NAMES.items():
        result = getattr(v, field)
        detail = ""
        if field in VERIFY_NEEDS_PERMISSION and result == dv.NOT_CHECKED:
            detail = VERIFY_PERMISSION_NOTE
        elif field == "revocation" and result == dv.NOT_CHECKED:
            detail = ("NOT CHECKED: OCSP and CRL lookups are network calls and this ran "
                      "offline. Nothing was found revoked; nothing was looked up")
        checks.append({"name": sentence, "field": field, "result": result,
                       "detail": detail})
    return {"document_id": did, "sha256": row["sha256"], "name": row.get("name"),
            "checks": checks,
            "overall": v.overall_status,
            # The module's own sentence, not one written here: it is built from the parts and
            # cannot contradict them.
            "sentence": v.sentence(),
            "complete": v.overall_status == dv.COMPLETE,
            "note": ("COMPLETE only when every required check is established. Two checks "
                     "need a permission this deployment does not hold and are NOT_CHECKED, "
                     "so a genuine document reports INCOMPLETE_VERIFICATION today -- which "
                     "is what not having looked actually means")}


def _document_check(args: dict, ctx: Context) -> dict:
    """Verify, date, decide and RECORD. The Document Check, end to end. A WRITE verb.

    Three layers, each already proved on its own, joined here and nowhere else:
      `document.verify`          was it signed, and are the bytes unchanged (move 8)
      `checker/doc_validity`     is it still in force at `as_of` (move 9)
      `doc_validity.act`         what a lawyer should DO, with the reason (move 10)

    The row goes in `document_checks` (023), APPEND-ONLY. A certificate valid in March is
    expired in October: the same bytes produce a different action, and overwriting would lose
    "what did we tell them in March" -- the question that matters when a client asks why they
    were not warned.
    """
    from datetime import date as _date
    from checker import doc_validity as dval
    from checker import doc_verification as dver

    verified = _document_verify(args, ctx)
    if verified.get("status") == "REFUSED":
        # A refusal stands as a refusal. Recording a check for a document we could not read
        # would put a judgement in the audit record where there was none.
        return verified

    as_of_raw = (args.get("as_of") or "").strip()
    try:
        as_of = _date.fromisoformat(as_of_raw) if as_of_raw else _date.today()
    except ValueError:
        return _refuse("BAD_REQUEST",
                       f"as_of must be an ISO date (YYYY-MM-DD); got {as_of_raw!r}. Not "
                       f"defaulted to today: a date nobody meant would silently answer a "
                       f"different question from the one asked")

    did = verified["document_id"]
    chunks = ctx.store.read_vault_chunks() if ctx.store else []
    text = "\n".join(str(c.get("text") or "") for c in chunks
                      if c.get("document_id") == did)

    validity = dval.decide(
        text, as_of=as_of,
        superseded_by=str(args.get("superseded_by") or ""),
        revoked_on=(_date.fromisoformat(args["revoked_on"])
                    if str(args.get("revoked_on") or "").strip() else None))

    not_checked = tuple(c["name"] for c in verified["checks"]
                        if c["result"] == dver.NOT_CHECKED)
    action = dval.act(validity, verification_status=verified["overall"],
                      not_checked=not_checked,
                      renewable=_affirmed(args.get("renewable")))

    row = None
    if ctx.store is not None:
        import uuid
        row = ctx.store.write_document_check({
            "check_id": str(uuid.uuid4()), "document_id": did,
            "as_of": as_of.isoformat(), "checked_at": _now(ctx),
            "verification_status": verified["overall"],
            "validity_status": validity.status,
            "action": action.action, "action_reason": action.reason,
            "expires_on": (validity.expires_on.isoformat()
                           if validity.expires_on else None),
            "renew_by": action.renew_by.isoformat() if action.renew_by else None,
            # The held text the validity rule rested on, in the identity `runs` uses (008).
            # Empty when no rule fired, which is NOT RECORDED rather than "read no law".
            "law_versions": None})
    return {"document_id": did, "name": verified.get("name"),
            "as_of": as_of.isoformat(),
            "verification": {"overall": verified["overall"],
                             "checks": verified["checks"],
                             "sentence": verified["sentence"]},
            "validity": validity.to_dict(),
            "action": action.to_dict(),
            "check_id": (row or {}).get("check_id"),
            "recorded": row is not None,
            "note": ("Three separate questions, answered separately: was it signed, is it "
                     "still in force, and what should be done. An action is never a "
                     "statement that the document is legally valid -- NEEDS_LAWYER is the "
                     "answer whenever a check was not run, because KEEP would assert we "
                     "looked and found nothing wrong. Today the validity question is "
                     "NOT_DETERMINED for every document: no registry says which document "
                     "class expires under which provision, and this deployment will not "
                     "take a validity period from a caller, because a quote nobody checked "
                     "against the held corpus is not a provision.")}


def _documents_upload(args: dict, ctx: Context) -> dict:
    """Store bytes under their own sha256. The identity IS the hash, not a counter.

    `cannot_read` records a file whose text could NOT be extracted -- a scan, a
    photographed page -- with the reason. Without it such a file could only be left out of
    the upload, and then the conversation's file panel would not show the document the user
    attached at all: "we could not read your scan" would render as silence, which is the
    failure `checker/pdf_pages` exists to refuse, one layer out. Text is not required in
    that case, because there is none; everything else about the file is.

    Extraction itself is not done here. `checker/pdf_pages` is offline tooling whose own
    test asserts the served path imports no PDF reader, so the caller extracts and this
    verb records what happened.
    """
    import hashlib
    text = args.get("text") or ""
    cannot = (args.get("cannot_read") or "").strip()
    if not text.strip() and not cannot:
        return _refuse("BAD_REQUEST",
                       "text is required, or cannot_read with the reason it could not be "
                       "extracted")
    if cannot and len(cannot) < 20:
        return _refuse("BAD_REQUEST",
                       f"cannot_read must say WHY in words, got {cannot!r}. A file shown "
                       f"as unreadable with no reason invites the reader to assume the "
                       f"document was empty")
    name = args.get("name") or "document"
    seed = text if text.strip() else f"{name}\u0000{cannot}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    record = {"sha256": digest, "bytes": len(text.encode("utf-8")),
              "name": name, "tenant": ctx.tenant, "text": text}
    if cannot:
        record["cannot_read"] = cannot
    ctx.documents[digest] = record
    return {"document_id": digest, "sha256": digest,
            "bytes": record["bytes"],
            "state": ("CANNOT_READ" if cannot else "READ"),
            "reason": cannot or None,
            "stored": "memory",
            "note": ("Held in a temporary process cache that may expire or evict it and "
                     "does not survive a restart. Use the vault for durable documents.")}
