"""Drafts (H3): create, revise, versions, diff, export, list; draft prose."""
from __future__ import annotations

import re

from gateway import access
from gateway.verbs import ask_layers, model_access
from gateway.verbs.ask_layers import _critic_enabled
from gateway.verbs.core import Context, _refuse


def _draft_prose(template: str, source: dict, ctx: Context) -> tuple[list, str]:
    """(blocks, note) for a draft's connecting sentences. Never raises.

    The clearance lives HERE, with every other model call, and not in
    `checker/draft_prose.py`, which is pure. Which origin a draft's facts need is decided
    by what those facts ARE:

      research_memo   the citations' own corpus files -> PUBLIC, `clear_file`
      client_email    playbook findings, which carry values read out of the client's
                      contract -> MATTER, `clear_matter`, and D3 applies

    So while the deployment region is unconfirmed an email gets NO prose and a note saying
    exactly that, and the draft is still built from the findings. That is not a
    degradation to paper over: it is the residency rule working, and the note is how a
    user learns the difference between "we chose not to" and "we could not".
    """
    from checker import draft_prose, public_only, router
    try:
        sensitivity = draft_prose.sensitivity_of(template)
    except draft_prose.ProseError as e:
        return [], f"{draft_prose.NO_PROSE_PREFIX}{e}"

    facts = draft_prose.facts_for(template, source)
    if not facts:
        return [], (f"{draft_prose.NO_PROSE_PREFIX}the source run carries no findings to "
                    f"write about")
    try:
        if sensitivity == draft_prose.PUBLIC:
            # The citations' own files. A quote we are about to send is cleared against
            # the corpus file it was read from, not asserted public by this function.
            origins = tuple(public_only.clear_file(str(c.get("source")))
                            for c in (source.get("citations") or ())
                            if str(c.get("source") or ""))
            if not origins:
                return [], (f"{draft_prose.NO_PROSE_PREFIX}no citation in this run names "
                            f"the file it was read from, so nothing can be cleared")
            question = str(source.get("question") or "").strip()
            if question:
                typed, blocked = model_access._typed_text_origin(question, name="draft question",
                                                    task="draft_prose", ctx=ctx)
                if blocked:
                    return [], f"{draft_prose.NO_PROSE_PREFIX}{blocked['detail']}"
                origins = origins + (typed,)
        else:
            origins = (public_only.clear_matter(
                draft_prose.matter_text(facts), name=f"{template} findings",
                provider=router.AZURE),)
    except Exception as e:                                       # noqa: BLE001
        return [], (f"{draft_prose.NO_PROSE_PREFIX}these findings could not be cleared to "
                    f"leave the device ({type(e).__name__})")

    served, refusal = model_access._served_or_refusal(origins, name="draft_prose",
                                         purpose=router.NARRATION, ctx=ctx,
                                         consequence=router.LOW)
    if refusal:
        return [], (f"{draft_prose.NO_PROSE_PREFIX}no model could be served "
                    f"({refusal['code']}): {str(refusal.get('detail') or '')[:160]}")
    blocks, note = draft_prose.write(template, source, model=served.call)
    if blocks and _critic_enabled():
        blocks, note = _critic_prose(blocks, note, ctx)
    return blocks, note


def _critic_prose(blocks, note: str, ctx: Context):
    """Run the critic over model-written draft prose. Job 6b.

    The same rules as everywhere else -- flag or remove, at most one removal, never
    rewrite -- applied to the sentences a model wrote for a draft. A removed sentence is
    gone from the draft, and the note says so: the prose is optional embellishment, so
    losing one costs nothing a reader needed, while leaving in a sentence the critic
    objected to costs exactly what this layer exists to prevent.
    """
    from checker import critic as cr
    claims = [{"id": f"p{i}", "text": str(b.get("text") or "")}
              for i, b in enumerate(blocks, 1)]
    try:
        verdict = cr.review(claims, critique=ask_layers._critic_for(ctx))
    except cr.CriticError:
        return blocks, note
    if not verdict.removed:
        return blocks, note
    gone = {i for i, _ in verdict.removed}
    kept = [b for i, b in enumerate(blocks, 1) if f"p{i}" not in gone]
    extra = (f"the critic removed {len(verdict.removed)} sentence(s) of connecting prose "
             f"({'; '.join(r for _, r in verdict.removed)[:160]})")
    return kept, (f"{note}; {extra}" if note else extra)


# ── H3: drafts ───────────────────────────────────────────────────────────────
#
# `checker/draft_versions.py` holds the history and the diff; `checker/provenance_slots.py`
# types every value and is what blocks approval. These verbs are the surface.

def _slots_from(raw) -> tuple:
    """Wire slots -> Slot objects. A malformed one is refused, never dropped."""
    from checker.provenance_slots import Slot
    out = []
    for i, item in enumerate(raw or ()):
        if not isinstance(item, dict):
            raise ValueError(f"slots[{i}] must be an object")
        out.append(Slot(name=str(item.get("name") or ""),
                        value=str(item.get("value") or ""),
                        slot_type=str(item.get("type") or item.get("slot_type") or ""),
                        source=str(item.get("source") or ""),
                        working=str(item.get("working") or ""),
                        note=str(item.get("note") or "")))
    return tuple(out)


def _draft_history(ctx: Context, draft_id: str):
    """(History, the draft row) or (None, None). Rebuilt from the store every time."""
    from checker.draft_versions import History, Version
    from checker.provenance_slots import Slot

    row = ctx.store.read_draft(draft_id)
    if row is None or not access.row_allowed(ctx, row):
        return None, None  # 028. Someone else's draft reads as no draft.
    versions = []
    for v in ctx.store.read_draft_versions(draft_id):
        slots = tuple(Slot(name=s.get("name") or "", value=s.get("value") or "",
                           slot_type=s.get("type") or s.get("slot_type") or "UNKNOWN",
                           source=s.get("source") or "", working=s.get("working") or "",
                           note=s.get("note") or "")
                      for s in v.get("slots") or ())
        versions.append(Version(
            draft_id=draft_id, version=v["version"], title=v["title"],
            body=v.get("body") or "", slots=slots,
            citations=tuple(v.get("citations") or ()),
            created_at=v.get("created_at") or "2026-01-01T00:00:00+00:00",
            approved_by=v.get("approved_by") or "",
            approved_at=v.get("approved_at") or ""))
    return History(draft_id, tuple(versions)), row


def _save_version(ctx: Context, draft_id: str, *, title: str, body: str, slots: tuple,
                  citations: tuple, approved_by: str = "", approved_at: str = "",
                  version: int | None = None) -> int:
    """Persist one version, with blocking_count from the same call that gates approval.

    A1. `version` is passed EXPLICITLY by `_draft_revise` -- `base_version + 1` -- so
    012_drafts.sql's PRIMARY KEY (draft_id, version) is what arbitrates two concurrent
    saves. Leaving it None computes `len(rows) + 1` at write time, which is what let two
    writers who both read v1 produce v2 and v3 and both succeed: a lost update with no
    conflict. A read-then-check in the handler alone cannot fix that, because the check and
    the write are not one step; the unique key is.
    """
    from checker.draft_versions import draft_blockers
    return ctx.store.append_draft_version({
        "draft_id": draft_id, "title": title, "body": body,
        **({} if version is None else {"version": int(version)}),
        "slots": [s.to_dict() for s in slots], "citations": list(citations),
        # Use the same body/provenance gate as Version.ready and exports.
        "blocking_count": len(draft_blockers(body, slots)),
        "approved_by": approved_by or None, "approved_at": approved_at or None})


# A draft nobody typed. NOT a statutory document type: `draft.create` defaulted to
# "agm_notice", which is an instrument carrying s.96 and s.101 obligations, for any caller
# who did not say otherwise. A title is not a type declaration, and `doc_classifier` already
# states the rule this broke -- "a guess here misfiles a document a lawyer then cannot find".
DRAFT_KIND_UNKNOWN = "unknown"


def _draft_create(args: dict, ctx: Context) -> dict:
    """Start a draft at version 1. A WRITE verb, so it is off MCP."""
    import uuid
    if ctx.store is None:
        return _refuse("NO_STORE", "a draft is a durable document; it needs a store")
    raw_title = args.get("title") or ""
    if not isinstance(raw_title, str):
        return _refuse("BAD_REQUEST", "title must be a string")
    title = raw_title.strip()
    if not title:
        return _refuse("BAD_REQUEST", "a draft needs a title")
    if len(title) > 200:
        return _refuse("BAD_REQUEST", "a draft title must be 200 characters or fewer")
    try:
        slots = _slots_from(args.get("slots"))
    except Exception as e:                                      # noqa: BLE001
        return _refuse("BAD_REQUEST", f"slots: {e}")
    body = args.get("body") or ""
    if not isinstance(body, str):
        return _refuse("BAD_REQUEST", "body must be a string")
    if len(body) > 100_000:
        return _refuse("BAD_REQUEST", "draft text must be 100000 characters or fewer")
    citations = args.get("citations")
    if citations is None:
        citations = []
    if not isinstance(citations, list):
        return _refuse("BAD_REQUEST", "citations must be an array")
    draft_id = (args.get("draft_id") or "").strip() or str(uuid.uuid4())
    from gateway.store import StoreError
    from checker.draft_versions import draft_blockers
    try:
        n = ctx.store.create_draft(
            {"draft_id": draft_id, "kind": args.get("kind") or DRAFT_KIND_UNKNOWN,
             "title": title, "actor_id": ctx.actor},
            {"title": title, "body": body, "slots": [s.to_dict() for s in slots],
             "citations": citations,
             "blocking_count": len(draft_blockers(body, slots))})
    except StoreError:
        return _refuse("CREATE_CONFLICT", "The draft could not be created. If this ID "
                       "already exists, open it and save a revision with its current version.")
    return _draft_status(ctx, draft_id, version=n,
                         note="Version 1 saved. Every save is a new version; nothing is "
                              "edited in place.")


def _draft_revise(args: dict, ctx: Context) -> dict:
    """Save a NEW version. Never edits one or records a formal approval."""
    if ctx.store is None:
        return _refuse("NO_STORE", "no store is configured")
    draft_id = (args.get("draft_id") or "").strip()
    if not draft_id:
        return _refuse("BAD_REQUEST", "draft_id is required")
    if "approved_by" in args:
        return _refuse(
            "IDENTITY_REQUIRED",
            "draft approval is unavailable through draft.revise. A reviewer decision must "
            "use an authenticated actor; a caller-supplied name is not identity.")
    history, row = _draft_history(ctx, draft_id)
    if history is None:
        return _refuse("NOT_FOUND", f"no draft {draft_id!r} for this tenant")
    latest = history.latest

    # A1. The optimistic lock. `base_version` is REQUIRED: a revise that does not say what
    # it was based on cannot be checked, and defaulting it to "the latest" is the lost
    # update with extra steps.
    raw_base = args.get("base_version")
    if raw_base is None or str(raw_base).strip() == "":
        return _refuse("BAD_REQUEST",
                       "base_version is required: it is the version this revision was "
                       "based on, and without it a concurrent save would overwrite a "
                       "colleague's work instead of being told about it")
    try:
        base_version = int(str(raw_base).strip())
    except (TypeError, ValueError):
        return _refuse("BAD_REQUEST", f"base_version must be a number, got {raw_base!r}")

    latest_version = latest.version if latest else 0
    if base_version != latest_version:
        return {
            "status": "REFUSED", "code": "CONFLICT",
            "detail": (f"this revision was based on version {base_version}, but the draft "
                       f"is now at version {latest_version}. Another save got there first. "
                       f"Re-read version {latest_version} and revise from it -- nothing has "
                       f"been overwritten and nothing has been merged"),
            # Typed, not only in the prose: a client that has to re-read needs the number
            # without parsing an English sentence.
            "draft_id": draft_id,
            "base_version": base_version,
            "latest_version": latest_version,
        }

    try:
        slots = (_slots_from(args["slots"]) if "slots" in args
                 else tuple(latest.slots if latest else ()))
    except Exception as e:                                      # noqa: BLE001
        return _refuse("BAD_REQUEST", f"slots: {e}")
    raw_title = args.get("title")
    if raw_title is not None and not isinstance(raw_title, str):
        return _refuse("BAD_REQUEST", "title must be a string")
    title = raw_title or (latest.title if latest else row["title"])
    body = args.get("body") if args.get("body") is not None else (
        latest.body if latest else "")
    if not isinstance(title, str) or not title.strip():
        return _refuse("BAD_REQUEST", "a draft needs a title")
    if len(title.strip()) > 200:
        return _refuse("BAD_REQUEST", "a draft title must be 200 characters or fewer")
    if not isinstance(body, str):
        return _refuse("BAD_REQUEST", "body must be a string")
    if len(body) > 100_000:
        return _refuse("BAD_REQUEST", "draft text must be 100000 characters or fewer")
    # Edits invalidate the previous evidence-to-text binding. A caller cannot remove
    # this server-owned marker by submitting an empty or relabelled slot list.
    from checker.draft_versions import REVISION_REVIEW
    from checker.provenance_slots import Slot, UNKNOWN
    needs_review = bool(latest and (
        body != latest.body or any(s.name == REVISION_REVIEW for s in latest.slots)))
    slots = tuple(s for s in slots if s.name != REVISION_REVIEW)
    if needs_review:
        slots += (Slot(REVISION_REVIEW, "", UNKNOWN,
                       note="The draft text changed. Recheck its facts and citations. "
                            "Formal sign-off requires authenticated review, which is "
                            "not available through Save."),)
    citations = tuple(args.get("citations") or (latest.citations if latest else ()))

    try:
        n = _save_version(ctx, draft_id, title=title, body=body, slots=slots,
                          citations=citations, version=base_version + 1)
    except Exception as e:                                      # noqa: BLE001
        # The race the check above cannot close: two writers both passed it and both tried
        # to write base_version + 1. The PRIMARY KEY refused the second, and it gets the
        # same typed CONFLICT -- a loser must not be able to tell which of the two paths
        # refused it, because the remedy is identical.
        current = _draft_history(ctx, draft_id)[0]
        now_at = current.latest.version if (current and current.latest) else latest_version
        return {"status": "REFUSED", "code": "CONFLICT",
                "detail": (f"another save wrote version {base_version + 1} first "
                           f"({e}). The draft is at version {now_at}; re-read it and "
                           f"revise from there"),
                "draft_id": draft_id, "base_version": base_version,
                "latest_version": now_at}
    return _draft_status(ctx, draft_id, version=n,
                         note="Saved as a new version. Formal approval is a separate action.")


def _draft_status(ctx: Context, draft_id: str, *, version=None, note: str = "") -> dict:
    history, row = _draft_history(ctx, draft_id)
    if history is None:
        return _refuse("NOT_FOUND", f"no draft {draft_id!r} for this tenant")
    latest = history.latest
    ready = bool(latest and latest.ready)
    from checker.draft_versions import review_items
    return {"draft_id": draft_id, "title": row["title"], "kind": row.get("kind"),
            "versions": len(history.versions), "version": version or (
                latest.version if latest else 0),
            "ready_for_approval": ready,
            # A draft with an unsupported slot needs a PERSON, which is what NEEDS_LAWYER
            # means. `_envelope_for` reads this, so a DRAFT turn does not come back
            # ANSWERED while a slot is still blank -- "here is your document" about a
            # document nobody has written is the worst thing this envelope could say.
            "requires_review": not ready,
            "blocking": [s.name for s in (latest.blockers() if latest else ())],
            "review_items": review_items(latest.body, latest.slots) if latest else [],
            "approved": bool(latest and latest.approved),
            "approved_by": (latest.approved_by or None) if latest else None,
            "note": note or ("A MODEL_SUGGESTION or UNKNOWN slot blocks approval: a "
                             "fluent sentence is not evidence of anything, and a blank "
                             "in a legal document is not a small problem.")}


def _draft_versions(args: dict, ctx: Context) -> dict:
    """Every version of a draft, in order. Read-only."""
    if ctx.store is None:
        return _refuse("NO_STORE", "no store is configured")
    draft_id = (args.get("draft_id") or "").strip()
    if not draft_id:
        return _refuse("BAD_REQUEST", "draft_id is required")
    history, row = _draft_history(ctx, draft_id)
    if history is None:
        return _refuse("NOT_FOUND", f"no draft {draft_id!r} for this tenant")
    return {"draft_id": draft_id, "title": row["title"],
            "versions": [v.to_dict() for v in history.versions],
            "note": ("Append-only: a version is never edited, so an earlier one is "
                     "exactly what was written then -- including what was NOT supported "
                     "and why.")}


def _draft_diff(args: dict, ctx: Context) -> dict:
    """The exact diff between two versions: the text, and the provenance."""
    from checker.draft_versions import VersionError, diff as _diff

    if ctx.store is None:
        return _refuse("NO_STORE", "no store is configured")
    draft_id = (args.get("draft_id") or "").strip()
    if not draft_id:
        return _refuse("BAD_REQUEST", "draft_id is required")
    history, _row = _draft_history(ctx, draft_id)
    if history is None:
        return _refuse("NOT_FOUND", f"no draft {draft_id!r} for this tenant")
    try:
        a = history.at(int(args.get("from_version") or 1))
        b = history.at(int(args.get("to_version") or (history.latest.version
                                                      if history.latest else 1)))
    except (VersionError, ValueError, TypeError) as e:
        return _refuse("BAD_REQUEST", str(e))
    return _diff(a, b)


def _draft_export(args: dict, ctx: Context) -> dict:
    """One version as text or .docx. The .docx is written with the standard library."""
    import base64
    from checker.draft_versions import VersionError, to_docx, to_text

    if ctx.store is None:
        return _refuse("NO_STORE", "no store is configured")
    draft_id = (args.get("draft_id") or "").strip()
    if not draft_id:
        return _refuse("BAD_REQUEST", "draft_id is required")
    history, row = _draft_history(ctx, draft_id)
    if history is None:
        return _refuse("NOT_FOUND", f"no draft {draft_id!r} for this tenant")
    fmt = (args.get("format") or "docx").strip().lower()
    if fmt not in ("docx", "text"):
        return _refuse("BAD_REQUEST", f"format must be docx or text, got {fmt!r}")
    try:
        v = history.at(int(args.get("version") or (history.latest.version
                                                   if history.latest else 1)))
    except (VersionError, ValueError, TypeError) as e:
        return _refuse("BAD_REQUEST", str(e))
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", row["title"])[:40].strip("-") or "draft"
    out = {"draft_id": draft_id, "version": v.version, "format": fmt,
           "filename": f"{safe}-v{v.version}.{'docx' if fmt == 'docx' else 'txt'}",
           "ready_for_approval": v.ready, "approved": v.approved,
           "note": ("An exported draft that is not approvable says so on its own face, "
                    "because the file travels away from this system.")}
    if fmt == "text":
        out["text"] = to_text(v)
        out["content_type"] = "text/plain"
        return out
    data = to_docx(v)
    out["content_type"] = ("application/vnd.openxmlformats-officedocument."
                           "wordprocessingml.document")
    out["bytes"] = len(data)
    # base64 because a verb returns JSON. The archive itself is deterministic, so the
    # same version always encodes identically and can be hashed or cached.
    out["docx_base64"] = base64.b64encode(data).decode("ascii")
    return out


def _draft_status_verb(args: dict, ctx: Context) -> dict:
    if ctx.store is None:
        return _refuse("NO_STORE", "no store is configured")
    draft_id = (args.get("draft_id") or "").strip()
    if not draft_id:
        return _refuse("BAD_REQUEST", "draft_id is required")
    return _draft_status(ctx, draft_id)


def _draft_list(args: dict, ctx: Context) -> dict:
    """List tenant-visible draft metadata only; document bodies stay out of the inbox."""
    import base64
    import json
    import uuid
    from datetime import datetime
    if ctx.store is None:
        return _refuse("NO_STORE", "drafts need a store")
    try:
        limit = int(str(args.get("limit") or "20"))
    except (TypeError, ValueError):
        return _refuse("BAD_REQUEST", "limit must be an integer from 1 to 50")
    if limit < 1 or limit > 50:
        return _refuse("BAD_REQUEST", "limit must be an integer from 1 to 50")
    before_updated_at = before_draft_id = None
    cursor = str(args.get("cursor") or "").strip()
    if cursor:
        try:
            raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
            payload = json.loads(raw)
            if not isinstance(payload, dict) or set(payload) != {"updated_at", "draft_id"}:
                raise ValueError("unexpected cursor shape")
            before_updated_at = str(payload["updated_at"])
            stamp = datetime.fromisoformat(before_updated_at.replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                raise ValueError("timestamp must include a timezone")
            before_draft_id = str(payload["draft_id"])
            if str(uuid.UUID(before_draft_id)) != before_draft_id:
                raise ValueError("draft id is not canonical")
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            return _refuse("BAD_REQUEST", f"invalid draft cursor: {exc}")
    rows = ctx.store.list_drafts(limit=limit + 1,
                                 before_updated_at=before_updated_at,
                                 before_draft_id=before_draft_id)
    # 028. Drafts are not filed to matters, so a draft is its author's. Postgres filters
    # this by policy; the check here keeps memory to the same rule.
    rows = [r for r in rows if access.row_allowed(ctx, r)]
    has_more = len(rows) > limit
    page = rows[:limit]
    next_cursor = None
    if has_more and page:
        tail = page[-1]
        packed = json.dumps({"updated_at": tail["updated_at"],
                             "draft_id": tail["draft_id"]},
                            separators=(",", ":")).encode("utf-8")
        next_cursor = base64.urlsafe_b64encode(packed).decode("ascii").rstrip("=")
    return {"drafts": page, "next_cursor": next_cursor, "scope": "author",
            "note": "Titles and review state of your drafts. Draft text is not included."}
