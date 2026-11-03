"""Shared by both backends: the errors, the `Backend` protocol, the row shapes and the checks that
keep a row honest, and small helpers."""
from __future__ import annotations

import re
import threading
from typing import Protocol


MEMORY = "in-memory"
POSTGRES = "postgres"

URL_ENV = "PLACEDON_DATABASE_URL"
# What invites.list may show. Never token_hash: the hash of a live token is what a
# stolen database dump would be matched against.
_PENDING_INVITE_COLS = ("invite_id", "email", "role", "invited_by", "created_at",
                        "expires_at")


def _when(value):
    """An expires_at, whatever form it was stored in, as an aware datetime."""
    from datetime import datetime, timezone
    if isinstance(value, datetime):
        d = value
    else:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                   r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


class StoreError(RuntimeError):
    """The store could not do what was asked. Never swallowed into a None."""


class TurnConflict(StoreError):
    """An idempotency key or a conversation matter was reused inconsistently."""


class RetryConflict(StoreError):
    """A FAILED document whose run is not FAILED: nothing was retried or changed."""


class DuplicateVaultDocument(StoreError):
    """The same content already has a tenant-scoped vault record.

    `document_id` names that record when the backend could read it back, so `vault.upload`
    can hand the caller the document they already have instead of a dead-end refusal.
    """

    def __init__(self, message: str, document_id: str | None = None) -> None:
        super().__init__(message)
        self.document_id = document_id


class Backend(Protocol):
    kind: str

    def write_run(self, run: dict) -> None: ...
    def read_run(self, run_id: str) -> dict | None: ...
    def put_document(self, *, sha256: str, name: str, byte_count: int) -> dict: ...
    def get_document(self, sha256: str) -> dict | None: ...
    def write_decision(self, decision: dict) -> dict: ...
    def read_decisions(self, run_id: str) -> list[dict]: ...
    def read_labels(self) -> list[dict]: ...
    # 8a: users, roles and invites (018_users_roles.sql).
    def write_actor(self, actor: dict) -> dict: ...
    def read_actor(self, actor_id: str) -> dict | None: ...
    def create_invite(self, invite: dict) -> dict: ...
    def accept_invite(self, token_hash: str, *, actor_id: str, now: str,
                      actor: dict | None = None) -> dict | None: ...
    def find_actor_by_email(self, email: str) -> dict | None: ...
    def read_invite(self, token_hash: str) -> dict | None: ...
    def list_actors(self) -> list[dict]: ...
    # 036: pending invites, and cancelling one (the row stays, marked).
    def list_pending_invites(self) -> list[dict]: ...
    def cancel_invite(self, invite_id: str, *, cancelled_by: str) -> bool: ...
    # 026: sessions. Tenant-scoped CREATE and REVOKE, run once a tenant is known
    # (DECISION_ACCOUNTS.md Decision 4). The cross-tenant RESOLVE-by-hash is deliberately
    # NOT here: it is the one tenant-blind read, done by AuthLookup via
    # auth_resolve_session (SECURITY DEFINER), never through a tenant-bound backend.
    def create_session(self, session: dict) -> dict: ...
    def revoke_session(self, token_hash: str) -> bool: ...
    def append_step(self, run_id: str, step: dict, *, key: str) -> bool: ...
    def set_run(self, run_id: str, *, status: str, refusal_code=None, result=None) -> None: ...
    # 031: live progress of a RUNNING run, display only (gateway/progress.py).
    def set_run_progress(self, run_id: str, progress: dict) -> None: ...
    def read_run_progress(self, run_id: str) -> dict | None: ...
    def read_failure_counts(self) -> list[dict]: ...
    def write_cascade(self, record: dict, *, run_id: str | None = None) -> dict: ...
    def read_cascades(self, *, run_id: str | None = None, limit: int = 1000) -> list[dict]: ...
    # C2: the chat layer (010_conversations.sql).
    def write_conversation(self, conversation: dict) -> dict: ...
    def read_conversation(self, conversation_id: str) -> dict | None: ...
    def list_conversations(self, *, matter_id: str, limit: int = 50) -> list[dict]: ...
    # 8b: matters (019_matters.sql).
    def write_matter(self, matter: dict, *, owner: str | None = None) -> dict: ...
    # V1: the vault (020_vault.sql).
    def write_vault_document(self, doc: dict, *, run: dict | None = None,
                             queue=None, queued: dict | None = None) -> dict: ...
    def read_vault_document(self, document_id: str) -> dict | None: ...
    def vault_documents_by_sha256(self, sha256: str) -> list[dict]: ...
    def list_vault_documents(self, *, matter_id: str) -> list[dict]: ...
    def browse_vault_documents(self, *, matter_id: str | None, query: str, limit: int, offset: int) -> list[dict]: ...
    def write_vault_chunks(self, document_id: str, chunks: list) -> int: ...
    def read_vault_chunks(self) -> list[dict]: ...
    def write_vault_tags(self, document_id: str, tags: list) -> int: ...
    def read_vault_tags(self, document_id: str) -> list[dict]: ...
    def delete_vault_document(self, document_id: str, *, now: str) -> bool: ...
    def fail_vault_document(self, document_id: str, reason: str) -> bool: ...
    def retry_vault_document(self, document_id: str, *, queue) -> bool: ...
    def vault_counts(self) -> dict: ...
    # T3 move 10 (023_document_checks.sql). APPEND-ONLY: one row per CHECK, never updated.
    def write_document_check(self, check: dict) -> dict: ...
    def read_document_checks(self, *, document_id: str = "",
                             limit: int = 100) -> list[dict]: ...
    def read_renewals(self, *, on_or_before: str = "") -> list[dict]: ...
    def list_matters(self) -> list[dict]: ...
    # 028: explicit, append-only matter grants.
    def matter_role(self, matter_id: str, actor_id: str) -> str | None: ...
    def matter_roles(self, actor_id: str) -> dict: ...
    def grant_matter_access(self, *, matter_id: str, actor_id: str, role: str,
                            granted_by: str, reason: str) -> dict: ...
    def revoke_matter_access(self, *, matter_id: str, actor_id: str, revoked_by: str,
                             reason: str) -> bool: ...
    def list_matter_memberships(self, matter_id: str, *, include_revoked: bool = False) -> list[dict]: ...
    def share_vault_document(self, document_id: str, *, by_actor: str, reason: str,
                             shared: bool = True) -> dict: ...
    def list_unowned(self) -> dict: ...
    # 032: the firm's company profile. Current facts only; set supersedes, never deletes.
    def read_company_profile(self) -> list[dict]: ...
    def set_company_profile(self, rows: list[dict], *, by_actor: str, reason: str) -> list[dict]: ...
    def reassign_work(self, kind: str, resource_id: str, *, by_actor: str, reason: str,
                      to_actor: str | None = None, to_matter: str | None = None) -> dict: ...
    def reserve_turn(self, conversation: dict, user: dict, assistant: dict, *,
                     request_id: str, payload_digest: str, queue=None, queued=None) -> tuple[dict, bool]: ...
    def find_turn(self, request_id: str, payload_digest: str) -> dict | None: ...
    def expire_pending_message(self, message_id: str, envelope: dict) -> bool: ...
    def update_message(self, message_id: str, *, task, run_id, envelope, metadata) -> bool: ...
    def append_message(self, message: dict) -> dict: ...
    def read_messages(self, conversation_id: str) -> list[dict]: ...
    def set_message_envelope(self, message_id: str, envelope: dict) -> bool: ...
    # H4: review grids (011_review_grids.sql).
    def write_grid(self, grid: dict) -> dict: ...
    def read_grid(self, grid_id: str) -> dict | None: ...
    def read_grid_cells(self, grid_id: str) -> list[dict]: ...
    def list_grids(self, *, limit: int, before_created_at: str | None = None,
                   before_grid_id: str | None = None) -> list[dict]: ...
    def pause_grid(self, grid_id: str, *, reason: str, not_dispatched: int) -> bool:
        """Record that the budget paused this table. False when there is no such grid.

        Restates 022's two CHECKs, so a row that could never exist in Postgres cannot be
        written here either -- the divergence `conformance()` has caught five times.
        """
        if not str(reason or "").strip():
            raise StoreError(
                "a paused table needs a reason (022 review_grids_pause_reason_iff_paused): "
                "a pause with no nameable cause is indistinguishable from a table nobody "
                "looked at")
        if int(not_dispatched) < 0:
            raise StoreError("cells_not_dispatched cannot be negative")
        row = self.grids.get(grid_id)
        if row is None:
            return False
        row["paused_budget"] = True
        row["pause_reason"] = str(reason)
        row["cells_not_dispatched"] = int(not_dispatched)
        return True

    def write_grid_cell(self, cell: dict, *, if_pending: bool = True) -> bool: ...
    def cancel_grid(self, grid_id: str) -> bool: ...
    # 022: the budget paused this table, and which cells it left undispatched.
    def pause_grid(self, grid_id: str, *, reason: str, not_dispatched: int) -> bool: ...
    # O9: the answer cache (014_answer_cache.sql).
    def write_cache_entry(self, entry: dict) -> bool: ...
    def read_cache_entry(self, lookup_key: str) -> dict | None: ...
    def bump_cache_stat(self, kind: str, *, day: str) -> None: ...
    def read_cache_stats(self) -> dict: ...
    # H3: drafts and their versions (012_drafts.sql).
    def write_draft(self, draft: dict, *, create_only: bool = False) -> dict: ...
    def create_draft(self, draft: dict, first_version: dict) -> int: ...
    def read_draft(self, draft_id: str) -> dict | None: ...
    def list_drafts(self, *, limit: int, before_updated_at: str | None = None,
                    before_draft_id: str | None = None) -> list[dict]: ...
    def append_draft_version(self, version: dict) -> int: ...
    def read_draft_versions(self, draft_id: str) -> list[dict]: ...


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _check_grid_page(limit: int, before_created_at, before_grid_id) -> None:
    """The same refusals on both backends, so a bad page fails alike on each."""
    if limit < 1 or limit > 51:
        raise StoreError("review table list page size must be from 1 to 51")
    if (before_created_at is None) != (before_grid_id is None):
        raise StoreError("a review table cursor needs both created_at and grid_id")
    if before_grid_id is not None and not _UUID.match(before_grid_id):
        raise StoreError("a review table cursor has an invalid grid_id")


def _grid_summary(g: dict, *, columns: int, documents: int, cells: int,
                  pending: int) -> dict:
    """One row of `list_grids`, identical in shape on both backends."""
    return {"grid_id": g["grid_id"], "name": g.get("name") or "",
            "created_at": g["created_at"], "cancelled_at": g.get("cancelled_at"),
            "paused_budget": bool(g.get("paused_budget")),
            "actor_id": g.get("actor_id"), "matter_id": g.get("matter_id"),
            "columns": columns, "documents": documents, "cells": cells,
            "pending": pending}


# ── in memory ────────────────────────────────────────────────────────────────

# The key set a step and a proposition ALWAYS have when read back. Postgres returns every
# column whether or not the writer supplied it; a dict returns what it was handed. Without
# normalising, `step["model"]` is a KeyError on memory and None on Postgres -- which is a
# divergence that only shows up on the backend the gate does not run.
STEP_KEYS = ("capability", "engine_capability", "status", "model", "degraded",
             "provider", "region", "cost_inr", "cost_note", "idempotency_key")
PROPOSITION_KEYS = ("status", "source_ref", "span_start", "span_end")

# What makes a retry safe. The key is DERIVED from (run_id, capability) by the worker, never
# generated, so the same step computed twice produces the same key and the second append is
# a no-op. Because cost_inr rides on the step row, that is also what stops a reclaimed job
# from billing the same call twice.
def step_key(run_id: str, capability: str) -> str:
    return f"{run_id}:{capability}"
# A human decision, as labelled data (PLAN_23 rule 5, migration 005). `quoted_span` is what
# the reviewer was SHOWN, attested by the surface that showed it -- not re-derived here.
DECISION_KEYS = ("decision_id", "run_id", "item_ref", "decision", "reason", "quoted_span",
                 "quote_viewed", "law_versions", "actor_id", "decided_at")

# Also in gateway/verbs.py and as a CHECK in 005_decisions.sql. "ok" is not a reason, and a
# label whose text is "ok" teaches a later evaluation nothing.
MIN_REASON_CHARS = 10

# What a stored cascade record always reads back with. `attempts` keeps its ORDER: stage 2
# only ran because stage 1 was rejected, and a record that has to be re-sorted to see that
# has lost the thing it was kept for.
# What a message ALWAYS has when read back, for the same reason STEP_KEYS exists: Postgres
# returns every column, a dict returns what it was handed, and `msg["envelope"]` must not be
# a KeyError on one backend and None on the other.
MESSAGE_KEYS = ("message_id", "conversation_id", "ordinal", "role", "text", "file_ids",
                "task", "run_id", "envelope", "metadata")
# 8b: matter_id is part of a conversation row on both backends. Without it in the shaped
# key set, a dict conversation has no matter and the memory listing matches nothing.
CONVERSATION_KEYS = ("conversation_id", "title", "created_at", "updated_at",
                     "matter_id", "actor_id")

# 'system' is not among them, and the database refuses it too (010). A system prompt
# belongs to the run, not to the conversation.
ROLES = ("user", "assistant")


class MessageShape(StoreError):
    """A message that the database's own CHECKs would refuse. Raised before it is written,
    so the memory backend and Postgres refuse the same rows."""


def _check_draft_version(row: dict) -> None:
    """012's CHECKs, in code, so both backends refuse the same rows.

    The one that matters is the last: a version recorded as approved while any slot still
    blocks approval. `checker/draft_versions.Version` will not construct it, 012 will not
    store it, and this is the third place -- because the memory backend reaches neither.
    """
    if not str(row.get("title") or "").strip():
        raise StoreError("a draft version needs a title")
    if not isinstance(row.get("slots") or [], list):
        raise StoreError("slots must be an array; NULL would mean we did not record where "
                         "anything came from")
    blocking = int(row.get("blocking_count") or 0)
    if blocking < 0:
        raise StoreError(f"blocking_count cannot be negative, got {blocking}")
    by, at = row.get("approved_by"), row.get("approved_at")
    if bool(by) != bool(at):
        raise StoreError("an approval carries both a reviewer and a time, or neither")
    if by is not None and not str(by).strip():
        raise StoreError("an unattributed approval is not an approval")
    if by and blocking:
        raise StoreError(
            f"a version cannot be approved by {str(by)[:24]!r} while {blocking} slot(s) "
            f"still block approval (012 draft_versions_no_approval_while_blocked). That "
            f"row is the record of a gate that did not hold")


def _insert_draft_version(connection, tenant_id: str, version: dict, number: int) -> None:
    connection.execute(
        "INSERT INTO draft_versions (draft_id, tenant_id, version, title, "
        "body, slots, citations, blocking_count, approved_by, approved_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (version["draft_id"], tenant_id, number, version.get("title") or "",
         version.get("body") or "", _json(list(version.get("slots") or [])),
         _json(list(version.get("citations") or [])),
         int(version.get("blocking_count") or 0),
         version.get("approved_by"), version.get("approved_at")))


def _check_message(row: dict) -> None:
    role = row.get("role")
    if role not in ROLES:
        raise MessageShape(f"role {role!r} is not one of {ROLES}; 'system' is deliberately "
                           f"absent -- a system prompt belongs to the run")
    if role == "user" and row.get("envelope") is not None:
        raise MessageShape("a user message carries no envelope")
    if role == "assistant" and list(row.get("file_ids") or []):
        raise MessageShape("an assistant message carries no file_ids")
    if not isinstance(row.get("ordinal"), int) or row["ordinal"] < 0:
        raise MessageShape(f"ordinal must be a non-negative integer, got "
                           f"{row.get('ordinal')!r}")
    if row.get("metadata") is not None and not isinstance(row["metadata"], dict):
        raise MessageShape("metadata must be an object or absent")
    env = row.get("envelope")
    if env is not None and not isinstance(env, dict):
        raise MessageShape(f"envelope must be an object or absent, got "
                           f"{type(env).__name__}")


DRAFT_VERSION_KEYS = ("draft_id", "version", "title", "body", "slots", "citations",
                      "blocking_count", "approved_by", "approved_at")

# 013 adds the three cost columns. They are in the SHAPED key set, so a cell read back from
# the dict has `cost_inr` as a key whose value is None -- not a KeyError on one backend and
# None on the other, which is the divergence STEP_KEYS exists to prevent.
GRID_CELL_KEYS = ("grid_id", "document_id", "column_name", "state", "value", "quote",
                  "reason", "provider", "cost_inr", "cost_note")

CASCADE_KEYS = ("cascade_id", "run_id", "status", "error", "attempts", "body_ids",
                "claim_count", "refusal_count", "total_cost_inr")

# O9. `served` is a counter and not in the shaped set: it is maintained by the store, not
# supplied by a caller.
CACHE_KEYS = ("lookup_key", "content_key", "question", "task", "as_of", "sources",
              "citations", "payload", "created_at")
# A stale find is NOT a miss. Counted apart so the hit rate cannot be flattered by folding
# "the law moved" into "we had not seen it".
CACHE_STATS = ("hits", "misses", "stale")

# V1. 020's state CHECK, named once so the dict and the database cannot disagree.
VAULT_STATES = ("PENDING", "INGESTED", "PARTIAL", "CANNOT_READ", "DELETED", "FAILED")
# 029. Stored text a person may read and attach: complete, or complete except named pages.
READABLE_VAULT_STATES = ("INGESTED", "PARTIAL")
VAULT_OCR_STATES = ("NOT_NEEDED", "NEEDED", "BLOCKED", "DONE")


class DecisionExists(StoreError):
    """One decision per item per run. A second one would overwrite the label."""


def _check_cascade(row: dict) -> None:
    """The invariants 007_cascade.sql states as CHECKs, refused in Python too.

    Both, because a backfill or a fixture reaches one and not the other -- and because the
    memory backend has no CHECK constraints at all, so without this the two backends would
    accept different records and the conformance suite would be testing nothing.
    """
    if row["status"] not in ("ANSWERED", "PARTIAL", "NEEDS_LAWYER", "FAILED"):
        raise StoreError(f"{row['status']!r} is not a cascade status")
    if (row["status"] == "FAILED") != bool(row.get("error")):
        raise StoreError(
            "a FAILED cascade carries its transport error and nothing else does. A refusal "
            "is a decision and a failure is not, and the two must not blur in the record.")
    cost = row.get("total_cost_inr")
    if cost is not None and float(cost) <= 0:
        raise StoreError(
            "a recorded cascade cost of 0 would claim the calls were free. UNPRICED is "
            "NULL; there is no free provider here.")


NO_CALL_NOTE = ("no model was called on this step, so there is nothing to price. This is "
                "not a cost of zero.")


def _critic_enabled_now():
    """Whether the critic is on, as `checker/critic.enabled()` answers it right now.

    None rather than False if that cannot be determined: NULL means NOT RECORDED, and
    False would claim we looked and it was off.
    """
    try:
        from checker import critic
        return bool(critic.enabled())
    except Exception:                                            # noqa: BLE001
        return None


MATTER_ROLES = ("owner", "member", "viewer")
VAULT_ACCESS_ACTIONS = ("share", "unshare", "reassign")


def _utcnow() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _check_grant(role: str, reason: str) -> None:
    """028's CHECKs, restated so memory refuses exactly what Postgres refuses."""
    if role not in MATTER_ROLES:
        raise StoreError(f"{role!r} is not a matter role; one of {MATTER_ROLES}")
    if not str(reason or "").strip():
        raise StoreError("a grant needs a reason (028 matter_memberships.grant_reason)")


def _membership(matter_id, actor_id, role, granted_by, reason) -> dict:
    import uuid as _uuid
    return {"membership_id": str(_uuid.uuid4()), "matter_id": str(matter_id),
            "actor_id": str(actor_id), "role": role, "granted_by": str(granted_by),
            "granted_at": _utcnow(), "grant_reason": str(reason), "revoked_at": None,
            "revoked_by": None, "revoke_reason": None}


def _lock_live_vault_document(c, document_id: str) -> bool:
    """Lock the document row unless it is deleted. Held until the caller's transaction
    ends, so `delete_vault_document` (which locks the same row) runs wholly before or
    wholly after a chunk/tag rewrite: a deleted document's text is never stored again."""
    return c.execute("SELECT 1 FROM vault_documents WHERE document_id = %s "
                     "AND deleted_at IS NULL FOR UPDATE", (document_id,)).fetchone() is not None


def _same_vault_scope(row: dict, matter_id, uploaded_by) -> bool:
    """028's two partial unique indexes: one per matter, one per uploader while unfiled."""
    matter_id = str(matter_id or "").strip() or None
    if row.get("matter_id") != matter_id:
        return False
    return matter_id is not None or (uploaded_by is not None
                                     and row.get("uploaded_by") == uploaded_by)


# 028. The four kinds of unfiled work an admin may give an owner or a matter:
# kind -> (memory attribute, table, id column, owner column, name column).
REASSIGNABLE = {
    "vault_document": ("vault_docs", "vault_documents", "document_id", "uploaded_by", "name"),
    "draft": ("drafts", "drafts", "draft_id", "actor_id", "title"),
    "review_grid": ("grids", "review_grids", "grid_id", "actor_id", "name"),
    "conversation": ("conversations", "conversations", "conversation_id", "actor_id", "title"),
}


# 028. Reassignment places ORPHANS only: filed work is reached by grants, and an owner's
# own unfiled work is never an admin's to take.
UNOWNED_ONLY = ("only unfiled work with no owner is reassigned; filed work is reached by "
                "grants, and an owner's own work is not reassigned")


def _access_event(kind, resource_id, action, by_actor, reason, *, from_actor=None,
                  to_actor=None, from_matter=None, to_matter=None) -> dict:
    if kind not in REASSIGNABLE:
        raise StoreError(f"{kind!r} is not reassignable; one of {sorted(REASSIGNABLE)}")
    if action not in VAULT_ACCESS_ACTIONS:
        raise StoreError(f"{action!r} is not an access change; one of {VAULT_ACCESS_ACTIONS}")
    if not str(reason or "").strip():
        raise StoreError("an access change needs a reason (028 access_events)")
    return {"resource_kind": kind, "resource_id": str(resource_id), "action": action,
            "by_actor": str(by_actor), "reason": str(reason),
            "from_actor": from_actor, "to_actor": to_actor,
            "from_matter": from_matter, "to_matter": to_matter, "at": _utcnow()}


def _matter_scope(matter_id) -> str:
    """The matter a listing is scoped to, or refuse. 8b: NO CROSS-MATTER LISTING.

    Required, with no "all matters" value -- not even None. A listing that can be called
    without a scope will be called without one, and the result is every client's work in
    one list, which is the exact shape of the accident this rule exists to prevent.

    Shared by both backends so the refusal is the same sentence and the same type on each.
    """
    want = str(matter_id or "").strip()
    if not want:
        raise StoreError(
            "a matter_id is required to list conversations (8b: no cross-matter "
            "listing). There is deliberately no value meaning 'all matters': a listing "
            "that can be called without a scope will be, and the result is every "
            "client's work in one list")
    return want


def failure_tag(status: str, refusal_code, result) -> tuple:
    """(category, reason) for a terminal run, or (None, None) when there is no failure.

    O8. Computed HERE, inside the one function every terminal write routes through, so a
    caller cannot forget to tag a run -- the same reasoning that puts cost_inr on the step
    row rather than asking each verb to remember it.

    `checker/failure_tags` is the authority on the words. This is Ring 2 reading Ring 0,
    which the firewall permits; the reverse would not be.
    """
    from checker import failure_tags as ft
    if str(status or "").upper() == "ANSWERED":
        return None, None
    try:
        return ft.classify({"status": status, "refusal_code": refusal_code,
                            "result": result})
    except ft.TagError:
        # A run we cannot even hand to the classifier is left UNTAGGED rather than given
        # a word. NULL reads as "not recorded", which is true.
        return None, None


def _copied(versions):
    """A law-version map is stored by value: the caller's dict is not the store's."""
    return None if versions is None else dict(versions)


def _shaped(row: dict, keys: tuple[str, ...]) -> dict:
    out = {k: row.get(k) for k in keys}
    if "law_versions" in keys:
        out["law_versions"] = _copied(out["law_versions"])
    if "quote_viewed" in keys:
        out["quote_viewed"] = bool(out["quote_viewed"])
    if "degraded" in keys:
        out["degraded"] = bool(row.get("degraded", False))
    if "cost_note" in keys and out.get("cost_inr") is None and not out.get("cost_note"):
        # A null cost ALWAYS carries a reason. Without this, a step with no model reads as
        # a blank -- and a blank beside a null is indistinguishable from a cost nobody
        # bothered to record, which is the ambiguity this whole change exists to remove.
        out["cost_note"] = NO_CALL_NOTE
    return out


# T3 move 10. Named explicitly and SELECTed by name, never `SELECT *`: `read_grid` was
# changed to do the same after a column added by a later migration arrived in a position the
# row unpacking did not expect.
_DOC_CHECK_COLS = ("check_id", "document_id", "checked_at", "as_of",
                   "verification_status", "validity_status", "action", "action_reason",
                   "expires_on", "renew_by", "law_versions")


def _doc_check_row(row) -> dict:
    """One document_checks row as a dict, with dates as ISO strings.

    ISO strings and not `date` objects, because MemoryBackend stores what the caller passed
    and the caller passes strings -- and `store.conformance` compares the two backends field
    by field. A type that differs between them is a divergence the conformance list exists
    to catch.
    """
    if row is None:
        return {}
    out = dict(zip(_DOC_CHECK_COLS, row))
    for k in ("checked_at", "as_of", "expires_on", "renew_by"):
        if out.get(k) is not None:
            out[k] = out[k].isoformat()
    # uuid columns come back as `uuid.UUID`, and MemoryBackend stores the `str` the caller
    # passed. `read_renewals()` returned the right ROW and `r["document_id"] == did` was
    # False, so the conformance check reported an empty result against a table that held it
    # -- and the check before it passed VACUOUSLY, for the same reason. Caught by
    # `store.conformance` running against both backends, which is the sixth divergence of
    # this shape it has found.
    for k in ("check_id", "document_id"):
        if out.get(k) is not None:
            out[k] = str(out[k])
    return out


_DRAFT_CREATE_LOCK = threading.Lock()


# One column list and one row mapper for both decision reads, so RETURNING and SELECT
# cannot drift apart -- they did once each for steps and propositions.
_DECISION_COLS = ("decision_id, run_id, item_ref, decision, reason, quoted_span, "
                  "quote_viewed, law_versions, actor_id, decided_at")


def _decision_row(r) -> dict:
    return {"decision_id": str(r[0]), "run_id": str(r[1]), "item_ref": r[2],
            "decision": r[3], "reason": r[4], "quoted_span": r[5],
            "quote_viewed": r[6], "law_versions": r[7],
            "actor_id": str(r[8]), "decided_at": r[9].isoformat()}


def _json(value):
    """A dict for a jsonb column, or NULL. psycopg adapts dicts only through Jsonb."""
    if value is None:
        return None
    from psycopg.types.json import Jsonb
    return Jsonb(value)
