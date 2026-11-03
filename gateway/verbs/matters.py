"""Matters, and administering matter access (028)."""
from __future__ import annotations

from gateway import access
from gateway.verbs.core import Context, _access_args, _affirmed, _boolean, _refuse


MATTER_ID_UNUSABLE = "That matter id cannot be used. Omit matter_id to get a new one."


def _matters_create(args: dict, ctx: Context) -> dict:
    """Open a matter. A WRITE verb, so it is off MCP by that rule already."""
    import uuid
    if ctx.store is None:
        return _refuse("NO_STORE", "a matter is durable; it needs a store")
    name = (args.get("name") or "").strip()
    if not name:
        return _refuse("BAD_REQUEST", "a matter needs a name")
    mid = (args.get("matter_id") or "").strip() or str(uuid.uuid4())
    # 028. CREATE only. A supplied id that already exists -- one this actor can see or
    # one it cannot -- is refused with one sentence, so the verb is not an oracle for
    # which matter ids are real and cannot rename a matter its caller does not own.
    if any(m["matter_id"] == mid for m in ctx.store.list_matters()):
        return _refuse("BAD_REQUEST", MATTER_ID_UNUSABLE)
    try:
        row = ctx.store.write_matter({"matter_id": mid, "name": name,
                                      "client_ref": args.get("client_ref") or ""},
                                     owner=ctx.actor)
    except Exception as e:                                       # noqa: BLE001
        if "matters_pkey" in str(e) or "UniqueViolation" in str(e) and "name" not in str(e):
            return _refuse("BAD_REQUEST", MATTER_ID_UNUSABLE)
        return _refuse("BAD_REQUEST", str(e)[:200])
    return dict(row, note=("Work is filed to a matter. Conversations are listed one "
                           "matter at a time; there is no 'all matters' listing."))


def _matters_list(args: dict, ctx: Context) -> dict:
    """Every matter in this tenant. Read-only, and deliberately NOT an MCP tool.

    `mcp=False`: a client list is the most commercially sensitive thing a firm has -- it
    names who they act for -- and there is no agent task that needs it. `read_only` is
    about whether a call changes anything; this is about whether a tool should be able to
    ask at all.
    """
    if ctx.store is None:
        return _refuse("NO_STORE", "no store is configured")
    # 028. Only matters this actor holds a grant on, each with its role; an admin sees
    # every matter's name, to administer access, but `role: null` where it holds none.
    return {"matters": access.visible_matters(ctx, ctx.store.list_matters())}


# ── 028: administering matter access ─────────────────────────────────────────
#
# Every grant is explicit and recorded with who made it and why. After 028 is applied no
# existing matter has a member, so an admin uses `matters.access_report` to see what needs
# granting, then `matters.grant` -- and `access.reassign` for unfiled work that predates
# uploader tracking. Nothing is inferred from tenant membership.

def _active_actor(ctx: Context, actor_id: str) -> dict | None:
    try:
        row = ctx.store.read_actor(actor_id)
    except Exception:                                            # noqa: BLE001
        return None
    return row if row and row.get("disabled_at") is None else None


def _admin_matter(ctx: Context, matter_id: str) -> dict | None:
    """The matter, for an admin, or the same refusal a missing matter gets."""
    if not any(m["matter_id"] == matter_id for m in ctx.store.list_matters()):
        return _refuse("NOT_FOUND", access.NOT_AVAILABLE)
    return None


def _matters_grant(args: dict, ctx: Context) -> dict:
    """Give one person a role on one matter. ADMIN-only, by role AND by database policy."""
    if ctx.store is None:
        return _refuse("NO_STORE", "no store is configured")
    refusal, a = _access_args(args, "matter_id", "actor_id", "role", "reason")
    if refusal:
        return refusal
    if a["role"] not in ("owner", "member", "viewer"):
        return _refuse("BAD_REQUEST", "role must be owner, member or viewer")
    refusal = _admin_matter(ctx, a["matter_id"])
    if refusal:
        return refusal
    if _active_actor(ctx, a["actor_id"]) is None:
        return _refuse("NOT_FOUND", "No active account with that id in this firm.")
    try:
        row = ctx.store.grant_matter_access(matter_id=a["matter_id"], actor_id=a["actor_id"],
                                            role=a["role"], granted_by=ctx.actor,
                                            reason=a["reason"])
    except Exception:                                            # noqa: BLE001
        return _refuse("FORBIDDEN", "This grant was refused.")
    return {"status": "GRANTED", "membership": row,
            "self_grant": a["actor_id"] == ctx.actor}


def _matters_revoke(args: dict, ctx: Context) -> dict:
    """End one person's access to one matter. Takes effect on their next request, and on
    any job of theirs still queued or running (gateway/worker.py re-checks)."""
    if ctx.store is None:
        return _refuse("NO_STORE", "no store is configured")
    refusal, a = _access_args(args, "matter_id", "actor_id", "reason")
    if refusal:
        return refusal
    refusal = _admin_matter(ctx, a["matter_id"])
    if refusal:
        return refusal
    try:
        revoked = ctx.store.revoke_matter_access(matter_id=a["matter_id"],
                                                 actor_id=a["actor_id"],
                                                 revoked_by=ctx.actor, reason=a["reason"])
    except Exception:                                            # noqa: BLE001
        return _refuse("FORBIDDEN", "This revocation was refused.")
    return {"status": "REVOKED" if revoked else "NO_ACTIVE_GRANT",
            "matter_id": a["matter_id"], "actor_id": a["actor_id"]}


def _matters_members(args: dict, ctx: Context) -> dict:
    """Who holds which role on one matter, and optionally the full grant history."""
    if ctx.store is None:
        return _refuse("NO_STORE", "no store is configured")
    matter_id = str(args.get("matter_id") or "").strip()
    refusal = _admin_matter(ctx, matter_id) if matter_id else _refuse(
        "BAD_REQUEST", "matter_id required")
    if refusal:
        return refusal
    return {"matter_id": matter_id, "memberships": ctx.store.list_matter_memberships(
        matter_id, include_revoked=_affirmed(args.get("include_revoked")))}


def _matters_access_report(args: dict, ctx: Context) -> dict:
    """What an admin must grant after 028: matters with no members, and unfiled work with
    no recorded owner -- documents, drafts, review tables, conversations. Names only, never
    their text."""
    if ctx.store is None:
        return _refuse("NO_STORE", "no store is configured")
    matters = []
    for m in ctx.store.list_matters():
        # ponytail: one membership read per matter; a single grouped query when firms
        # have thousands of matters.
        members = ctx.store.list_matter_memberships(m["matter_id"])
        matters.append({"matter_id": m["matter_id"], "name": m["name"],
                        "members": len(members),
                        "owners": sum(1 for g in members if g["role"] == "owner")})
    unowned = ctx.store.list_unowned()
    return {"matters": matters,
            "matters_without_members": [m["matter_id"] for m in matters if not m["members"]],
            "unowned": unowned,
            "note": ("Grant access with matters.grant, and give unowned work an owner or a "
                     "matter with access.reassign. Nothing here was granted automatically.")}


def _vault_share(args: dict, ctx: Context) -> dict:
    """Share one of YOUR unfiled documents with the whole firm, or stop sharing it."""
    if ctx.store is None:
        return _refuse("NO_STORE", "no store is configured")
    refusal, a = _access_args(args, "document_id", "reason")
    if refusal:
        return refusal
    row = ctx.store.read_vault_document(a["document_id"])
    if row is None or not access.document_allowed(ctx, row):
        return _refuse("NOT_FOUND", f"no vault document {a['document_id']!r} for this tenant")
    if row.get("matter_id") or str(row.get("uploaded_by") or "") != str(ctx.actor):
        return _refuse("FORBIDDEN", "Only the uploader can share an unfiled document. A "
                                    "filed document is shared by granting matter access.")
    # `is not False` here re-shared on "false": a string is not the boolean False.
    shared = _boolean(args.get("shared"), default=True)
    if shared is None:
        return _refuse("BAD_REQUEST", "shared must be true or false")
    try:
        out = ctx.store.share_vault_document(a["document_id"], by_actor=ctx.actor,
                                             reason=a["reason"], shared=shared)
    except Exception:                                            # noqa: BLE001
        return _refuse("FORBIDDEN", "This change was refused.")
    return {"status": "SHARED" if shared else "UNSHARED", "document_id": a["document_id"],
            "shared_with_firm_at": out.get("shared_with_firm_at")}


def _access_reassign(args: dict, ctx: Context) -> dict:
    """ADMIN: give one piece of UNFILED work an owner, file it to a matter, or both.

    How work that predates 028 -- with no recorded owner, so readable by nobody -- becomes
    reachable again, and how an admin hands on the unfiled work of someone who left. Filed
    work is never moved here: who reaches a matter is decided by its grants.
    """
    from gateway.store import REASSIGNABLE
    if ctx.store is None:
        return _refuse("NO_STORE", "no store is configured")
    refusal, a = _access_args(args, "kind", "id", "reason")
    if refusal:
        return refusal
    if a["kind"] not in REASSIGNABLE:
        return _refuse("BAD_REQUEST", f"kind must be one of {sorted(REASSIGNABLE)}")
    to_actor = str(args.get("to_actor") or "").strip() or None
    to_matter = str(args.get("to_matter") or "").strip() or None
    if not (to_actor or to_matter):
        return _refuse("BAD_REQUEST", "name to_actor, to_matter, or both")
    if to_actor and _active_actor(ctx, to_actor) is None:
        return _refuse("NOT_FOUND", "No active account with that id in this firm.")
    if to_matter:
        refusal = _admin_matter(ctx, to_matter)
        if refusal:
            return refusal
    try:
        out = ctx.store.reassign_work(a["kind"], a["id"], by_actor=ctx.actor,
                                      reason=a["reason"], to_actor=to_actor,
                                      to_matter=to_matter)
    except Exception:                                            # noqa: BLE001
        return _refuse("NOT_FOUND", "No unfiled item with that id.")
    return {"status": "REASSIGNED", "kind": a["kind"], "id": a["id"],
            "owner": out.get("owner") or out.get("uploaded_by") or out.get("actor_id"),
            "matter_id": out.get("matter_id")}
