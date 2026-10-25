#!/usr/bin/env python3
"""Who may use which matter. The ONE check every verb and the worker call (028).

The database enforces the same rule under row-level security
(gateway/migrations/028_matter_access.sql), so a query nobody remembered to check is still
filtered. This module is the application half, and it exists for three reasons the policy
alone cannot serve:

  * a refusal a person can read, identical for "no such matter" and "not yours", instead
    of an empty list or a row-level-security error;
  * read-only access refused BEFORE a write is attempted, not as a database exception;
  * the in-memory backend, which has no row-level security at all.

## The rule

  filed row (matter_id set)   readable by any active grant; writable by owner or member
  unfiled row                 readable and writable by its owner (`actor_id`, or a vault
                              document's `uploaded_by`); an unfiled vault document SHARED
                              firm-wide is readable by everyone in the firm
  no owner recorded           nobody -- a pre-028 unfiled document waits for an admin

Identity is `ctx.actor`, which gateway/app.py takes from the authenticated principal and
never from a request body.

Run: PYTHONPATH=. python3 gateway/access.py --test
"""
from __future__ import annotations

import re

__all__ = ["READ", "WRITE", "WRITE_ROLES", "NOT_AVAILABLE", "matter_role", "require_matter",
           "row_allowed", "document_allowed", "visible_matters", "is_admin", "readable_documents",
           "args_allowed", "job_allowed", "content_allowed"]

READ = "read"
WRITE = "write"
WRITE_ROLES = ("owner", "member")

# One sentence for a matter that does not exist and one this actor may not use. A
# different answer for the two is an oracle for which matter ids are real.
NOT_AVAILABLE = "No matter with that id is available to you."
READ_ONLY = "Your access to this matter is read-only."

_DOC_OWNER = "uploaded_by"
_CONTENT_HASH = re.compile(r"[0-9a-f]{64}")
_JOB_DOCUMENT_KEYS = ("document_id", "file_ids", "document_ids")


def _refuse(code: str, detail: str) -> dict:
    return {"status": "REFUSED", "code": code, "detail": detail}


def is_admin(ctx) -> bool:
    return getattr(ctx, "role", "") == "admin"


def matter_role(ctx, matter_id) -> str | None:
    """This actor's active role on `matter_id`, or None. Never inferred from the tenant."""
    store = getattr(ctx, "store", None)
    if store is None or not matter_id or not getattr(ctx, "actor", ""):
        return None
    try:
        return store.matter_role(str(matter_id), str(ctx.actor))
    except Exception:                                            # noqa: BLE001
        return None  # An unreadable grant is no grant.


def require_matter(ctx, matter_id, need: str = READ) -> dict | None:
    """None when this actor may `need` the matter; otherwise the refusal to return."""
    role = matter_role(ctx, matter_id)
    if role is None:
        return _refuse("NOT_FOUND", NOT_AVAILABLE)
    if need == WRITE and role not in WRITE_ROLES:
        return _refuse("FORBIDDEN", READ_ONLY)
    return None


def row_allowed(ctx, row, need: str = READ, *, owner_key: str = "actor_id") -> bool:
    """Whether this actor may `need` one stored row: a conversation, run, draft, grid or
    vault document. A row is filed (matter_id) or owned (owner_key), never neither."""
    if not row:
        return False
    matter = row.get("matter_id")
    if matter:
        role = matter_role(ctx, matter)
        return role is not None and (need == READ or role in WRITE_ROLES)
    actor = str(getattr(ctx, "actor", "") or "")
    owner = row.get(owner_key)
    if owner and actor and str(owner) == actor:
        return True
    return (need == READ and owner_key == _DOC_OWNER
            and bool(row.get("shared_with_firm_at")))


def document_allowed(ctx, row, need: str = READ) -> bool:
    return row_allowed(ctx, row, need, owner_key=_DOC_OWNER)


def readable_documents(ctx, rows):
    """The rows (documents, or chunks carrying their document's fields) this actor may read."""
    return [r for r in rows if document_allowed(ctx, r)]


def content_allowed(ctx, sha256: str) -> bool:
    """May this actor read the bytes with this content hash? Yes if the hash is in its own
    legacy upload cache, or belongs to a vault document it may read. A hash alone is never
    permission: the file store is content-addressed and would serve any file to anyone
    holding the hash."""
    documents = getattr(ctx, "documents", None) or {}
    if sha256 in documents:
        return True
    store = getattr(ctx, "store", None)
    if store is None:
        return False
    try:
        rows = store.vault_documents_by_sha256(sha256)
    except Exception:                                            # noqa: BLE001
        return False
    return any(document_allowed(ctx, r) for r in rows)


def visible_matters(ctx, matters: list) -> list:
    """Matters this actor holds a grant on, each with its role. An admin sees every
    matter's METADATA in order to administer it, marked `role: None` where no grant is held:
    seeing that a matter exists is not access to its contents."""
    store = getattr(ctx, "store", None)
    roles = {}
    if store is not None and getattr(ctx, "actor", ""):
        try:
            roles = store.matter_roles(str(ctx.actor))
        except Exception:                                        # noqa: BLE001
            roles = {}
    admin = is_admin(ctx)
    return [dict(m, role=roles.get(m["matter_id"])) for m in matters
            if admin or m["matter_id"] in roles]


def args_allowed(ctx, args: dict) -> bool:
    """May this actor do work over what `args` names? Any matter or conversation must be
    writable and every document readable. Used by runs.submit before a job exists, and
    by job_allowed when it runs."""
    store = getattr(ctx, "store", None)
    if store is None:
        return False
    args = args if isinstance(args, dict) else {}
    try:
        matter = args.get("matter_id")
        if matter and require_matter(ctx, matter, WRITE) is not None:
            return False
        cid = args.get("conversation_id")
        if cid and not row_allowed(ctx, store.read_conversation(str(cid)), WRITE):
            return False
        gid = args.get("grid_id")
        if gid and not row_allowed(ctx, store.read_grid(str(gid)), WRITE):
            return False
        for key in _JOB_DOCUMENT_KEYS:
            ids = args.get(key)
            for did in ([ids] if isinstance(ids, str) else ids or ()):
                did = str(did)
                # A review grid names documents by content hash; the vault by uuid.
                ok = (content_allowed(ctx, did) if _CONTENT_HASH.fullmatch(did)
                      else document_allowed(ctx, store.read_vault_document(did)))
                if not ok:
                    return False
    except Exception:                                            # noqa: BLE001
        return False  # A check that could not run is a refusal, never a pass.
    return True


def job_allowed(ctx, run_id: str, args: dict) -> bool:
    """May this job's actor still do this job? Checked by gateway/worker.py when the job
    starts AND again before its result is published, so a grant revoked while the job
    waited -- or while it ran -- stops it. The run itself must be writable too."""
    store = getattr(ctx, "store", None)
    if store is None:
        return False
    try:
        if not row_allowed(ctx, store.read_run(run_id), WRITE):
            return False
    except Exception:                                            # noqa: BLE001
        return False
    return args_allowed(ctx, args)


def _test() -> int:
    from dataclasses import dataclass
    from gateway.store import MemoryBackend

    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    @dataclass
    class Ctx:
        actor: str
        store: object
        role: str = "lawyer"

    print("access")
    s = MemoryBackend()
    A, B, V, ADM = "a" * 8, "b" * 8, "v" * 8, "d" * 8
    for actor, role in ((A, "lawyer"), (B, "lawyer"), (V, "lawyer"), (ADM, "admin")):
        s.write_actor({"actor_id": actor, "label": actor, "role": role})
    s.write_matter({"matter_id": "m1", "name": "Acme"}, owner=A)
    s.write_matter({"matter_id": "m2", "name": "Other"})
    s.grant_matter_access(matter_id="m1", actor_id=V, role="viewer", granted_by=ADM,
                          reason="read-only for review")
    a, b, v, adm = Ctx(A, s), Ctx(B, s), Ctx(V, s), Ctx(ADM, s, "admin")

    check(require_matter(a, "m1", WRITE) is None, "the creator owns the matter it made")
    nope, missing = require_matter(b, "m1"), require_matter(b, "no-such-matter")
    check(nope == missing and nope["code"] == "NOT_FOUND",
          "a same-firm lawyer with no grant gets EXACTLY the refusal a nonexistent matter gets")
    check(require_matter(v, "m1") is None and require_matter(v, "m1", WRITE)["code"] == "FORBIDDEN",
          "a matter viewer may read and may not write")
    check(require_matter(adm, "m1") is not None,
          "an admin is NOT a member by being an admin: contents need a grant")
    check([m["matter_id"] for m in visible_matters(b, s.list_matters())] == [],
          "matters.list for a lawyer with no grants is empty, not the firm's client list")
    check({m["matter_id"] for m in visible_matters(adm, s.list_matters())} == {"m1", "m2"},
          "...and an admin sees every matter's metadata, to administer it")
    check(sorted(m["matter_id"] for m in visible_matters(v, s.list_matters())) == ["m1"],
          "...and a viewer sees only the matter they were granted")

    filed = {"matter_id": "m1", "actor_id": B}
    check(row_allowed(a, filed) and not row_allowed(b, filed),
          "a FILED row follows the matter's grants, not who created it")
    mine = {"matter_id": None, "uploaded_by": A}
    check(document_allowed(a, mine) and not document_allowed(b, mine)
          and not document_allowed(adm, mine),
          "an unfiled document is uploader-private -- an admin included")
    check(document_allowed(b, dict(mine, shared_with_firm_at="2026-10-25"))
          and not document_allowed(b, dict(mine, shared_with_firm_at="2026-10-25"), WRITE),
          "...shared firm-wide it is readable by the firm, and still only the uploader's to change")
    check(not document_allowed(a, {"matter_id": None, "uploaded_by": None}),
          "an unfiled document with NO recorded uploader is readable by nobody")

    s.revoke_matter_access(matter_id="m1", actor_id=V, revoked_by=ADM, reason="left the team")
    check(require_matter(v, "m1") is not None, "a revoked grant is no grant, immediately")
    check(len(s.list_matter_memberships("m1", include_revoked=True)) == 2,
          "...and the revoked grant is kept, not deleted: the table is its own history")
    s.write_actor({"actor_id": A, "label": A, "role": "lawyer", "disabled_at": "2026-10-25"})
    check(s.matter_role("m1", A) is None and require_matter(a, "m1") is not None,
          "a disabled actor holds no matter role")

    print(f"\n{ok}/{ok + fail} passed")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        sys.exit(_test())
    print(__doc__)
