"""`MemoryBackend`: the in-memory store the gate runs on."""
from __future__ import annotations

from contextlib import nullcontext
from copy import deepcopy
from dataclasses import dataclass, field
import threading

from gateway.store.core import (CACHE_KEYS, CACHE_STATS, CONVERSATION_KEYS, DECISION_KEYS,
    DRAFT_VERSION_KEYS, DecisionExists, DuplicateVaultDocument, GRID_CELL_KEYS, MEMORY,
    MESSAGE_KEYS, MessageShape, PROPOSITION_KEYS, REASSIGNABLE, RetryConflict, STEP_KEYS,
    StoreError, TurnConflict, UNOWNED_ONLY, VAULT_STATES, _DRAFT_CREATE_LOCK,
    _PENDING_INVITE_COLS, _access_event, _check_cascade, _check_draft_version, _check_grant,
    _check_grid_page, _check_message, _copied, _critic_enabled_now, _grid_summary,
    _matter_scope, _membership, _now_iso, _same_vault_scope, _shaped, _utcnow, _when,
    failure_tag)


@dataclass
class MemoryBackend:
    """A dict, with the same decomposition discipline as Postgres so the tests can be one.

    It stores the run's parts separately rather than keeping the caller's dict, because a
    backend that hands back the very object it was given passes tests the database cannot:
    a caller mutating its own dict would appear to have written to the store.
    """
    kind: str = MEMORY
    tenant_id: str = "00000000-0000-0000-0000-000000000000"
    runs: dict = field(default_factory=dict)
    steps: dict = field(default_factory=dict)
    props: dict = field(default_factory=dict)
    documents: dict = field(default_factory=dict)
    decisions: dict = field(default_factory=dict)      # run_id -> [row]
    cascades: list = field(default_factory=list)
    conversations: dict = field(default_factory=dict)
    messages: dict = field(default_factory=dict)       # conversation_id -> [row]
    turn_requests: dict = field(default_factory=dict)
    _turn_lock: object = field(default_factory=threading.RLock, repr=False, compare=False)
    grids: dict = field(default_factory=dict)
    grid_cells: dict = field(default_factory=dict)     # grid_id -> {(doc, col): row}
    drafts: dict = field(default_factory=dict)
    draft_versions: dict = field(default_factory=dict)  # draft_id -> [row]
    vault_docs: dict = field(default_factory=dict)      # document_id -> row
    # T3 move 10. A LIST, not a dict keyed on document_id: 023 stores one row per CHECK and
    # a dict would be the overwrite the architect record rejected -- "a certificate valid in
    # March is expired in October, and the same bytes produce a different action".
    document_checks: list = field(default_factory=list)
    vault_chunks: dict = field(default_factory=dict)    # document_id -> [row]
    # 028. Append-only, like the tables: a revoke sets revoked_at, nothing is deleted.
    memberships: list = field(default_factory=list)
    access_events: list = field(default_factory=list)
    vault_tags: dict = field(default_factory=dict)      # document_id -> [row]
    matters: dict = field(default_factory=dict)         # matter_id -> row
    actors: dict = field(default_factory=dict)          # actor_id -> row
    invites: dict = field(default_factory=dict)         # invite_id -> row
    sessions: dict = field(default_factory=dict)        # session_id -> row
    # A LIST, append-only, mirroring login_attempts's shape: no tenant_id, and nothing
    # ever updates a row once written -- a brute-force count reads the recent tail.
    login_attempts: list = field(default_factory=list)
    cache: dict = field(default_factory=dict)           # lookup_key -> row
    cache_stats: dict = field(default_factory=dict)     # day -> {hits, misses, stale}
    # 032. Append-only: a change supersedes the current row and appends a new one.
    company_profile: list = field(default_factory=list)

    def read_company_profile(self) -> list[dict]:
        return [dict(r) for r in self.company_profile if r["superseded_at"] is None]

    def set_company_profile(self, rows: list[dict], *, by_actor: str, reason: str) -> list[dict]:
        import uuid
        from gateway.company_profile import same_fact
        if not str(reason or "").strip():
            raise StoreError("a company profile change needs a reason (032)")
        now = _utcnow()
        current = [r for r in self.company_profile if r["superseded_at"] is None]
        keep = [r for r in current if any(same_fact(r, n) for n in rows)]
        for r in current:
            if r not in keep:
                r.update(superseded_at=now, superseded_by=str(by_actor))
        for n in rows:
            if not any(same_fact(k, n) for k in keep):
                self.company_profile.append(dict(
                    n, fact_id=str(uuid.uuid4()), confirmed_by=str(by_actor),
                    confirmed_at=now, reason=str(reason), superseded_at=None,
                    superseded_by=None))
        return self.read_company_profile()

    # ── H3: drafts ───────────────────────────────────────────────────────────
    def write_draft(self, draft: dict, *, create_only: bool = False) -> dict:
        from datetime import datetime, timezone
        did = draft["draft_id"]
        if create_only and did in self.drafts:
            raise StoreError("draft already exists")
        self.drafts[did] = {"draft_id": did, "kind": draft.get("kind") or "unknown",
                            "title": draft.get("title") or "",
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                            "actor_id": self.drafts.get(did, {}).get(
                                "actor_id", draft.get("actor_id")),
                            "matter_id": None}
        self.draft_versions.setdefault(did, [])
        return dict(self.drafts[did])

    def create_draft(self, draft: dict, first_version: dict) -> int:
        """Publish metadata and version 1 only after both have been validated."""
        staged = MemoryBackend()
        staged.write_draft(draft, create_only=True)
        staged.append_draft_version(dict(first_version, draft_id=draft["draft_id"], version=1))
        did = draft["draft_id"]
        # Publish through a shared lock so competing creates cannot replace version 1.
        with _DRAFT_CREATE_LOCK:
            if did in self.drafts:
                raise StoreError("draft already exists")
            self.draft_versions[did] = staged.draft_versions[did]
            self.drafts[did] = staged.drafts[did]
        return 1

    def read_draft(self, draft_id: str) -> dict | None:
        row = self.drafts.get(draft_id)
        return dict(row) if row else None

    def list_drafts(self, *, limit: int, before_updated_at: str | None = None,
                    before_draft_id: str | None = None) -> list[dict]:
        if limit < 1 or limit > 51:
            raise StoreError("draft list page size must be from 1 to 51")
        rows = []
        for did, draft in self.drafts.items():
            versions = self.draft_versions.get(did, [])
            if not versions:
                continue
            latest = max(versions, key=lambda row: int(row["version"]))
            updated_at = draft.get("updated_at") or latest.get("created_at") or ""
            if before_updated_at is not None and (updated_at, did) >= (
                    before_updated_at, before_draft_id or ""):
                continue
            from checker.draft_versions import stored_review_count
            count = stored_review_count(latest.get("body") or "", latest.get("slots") or [],
                                        int(latest.get("blocking_count") or 0))
            rows.append({"draft_id": did, "kind": draft.get("kind") or "unknown",
                         "title": latest.get("title") or draft.get("title") or "",
                         "updated_at": updated_at, "version": int(latest["version"]),
                         "blocking_count": count,
                         "approved": bool(latest.get("approved_by")) and count == 0,
                         "actor_id": draft.get("actor_id"), "matter_id": None})
        return sorted(rows, key=lambda row: (row["updated_at"], row["draft_id"]),
                      reverse=True)[:limit]

    def append_draft_version(self, version: dict) -> int:
        """The new version number. Raises on a version that 012 would refuse."""
        did = version["draft_id"]
        if did not in self.drafts:
            raise StoreError(f"no draft {did!r} to append a version to")
        _check_draft_version(version)
        rows = self.draft_versions.setdefault(did, [])
        n = int(version.get("version") or len(rows) + 1)
        if any(r["version"] == n for r in rows):
            # 012's PRIMARY KEY (draft_id, version). Two concurrent saves cannot both be
            # version 3; the loser is told rather than overwriting a colleague's revision.
            raise StoreError(
                f"draft {did[:8]} already has version {n}. Another save got there first; "
                f"re-read and revise from the latest rather than overwriting it")
        row = _shaped(dict(version, version=n), DRAFT_VERSION_KEYS)
        row["slots"] = list(version.get("slots") or [])
        row["citations"] = list(version.get("citations") or [])
        from datetime import datetime, timezone
        # 012 stamps created_at DEFAULT now(); the memory backend must too, or every version
        # read back undated and was shown as 2026-01-01.
        row["created_at"] = version.get("created_at") or datetime.now(timezone.utc).isoformat()
        rows.append(row)
        self.drafts[did]["updated_at"] = datetime.now(timezone.utc).isoformat()
        self.drafts[did]["title"] = row.get("title") or self.drafts[did]["title"]
        return n

    def read_draft_versions(self, draft_id: str) -> list[dict]:
        return [dict(r) for r in sorted(self.draft_versions.get(draft_id, []),
                                        key=lambda r: r["version"])]

    # ── H4: review grids ─────────────────────────────────────────────────────
    def write_grid(self, grid: dict) -> dict:
        gid = grid["grid_id"]
        self.grids[gid] = {"grid_id": gid, "name": grid.get("name") or "",
                           "actor_id": self.grids.get(gid, {}).get(
                               "actor_id", grid.get("actor_id")),
                           "matter_id": None,
                           "columns": [dict(c) for c in grid.get("columns") or ()],
                           "document_ids": list(grid.get("document_ids") or ()),
                           # 034. Merged over any earlier write, as Postgres's `||` does.
                           "document_names": {**self.grids.get(gid, {}).get(
                               "document_names", {}),
                               **dict(grid.get("document_names") or {})},
                           "cancelled_at": self.grids.get(gid, {}).get("cancelled_at"),
                           # 011's DEFAULT now(), kept across a re-write as Postgres keeps it.
                           "created_at": self.grids.get(gid, {}).get("created_at")
                           or grid.get("created_at") or _now_iso(),
                           # 022's three columns, defaulted the way the migration defaults
                           # them: a grid nobody paused reads "never paused".
                           "paused_budget": self.grids.get(gid, {}).get(
                               "paused_budget", False),
                           "pause_reason": self.grids.get(gid, {}).get("pause_reason", ""),
                           "cells_not_dispatched": self.grids.get(gid, {}).get(
                               "cells_not_dispatched", 0)}
        cells = self.grid_cells.setdefault(gid, {})
        # Materialise every cell as PENDING, exactly as the Postgres path does. The shared
        # conformance list caught this on its first run: Postgres inserted the grid's cells
        # and the dict did not, so `read_grid_cells` was empty on one backend and four rows
        # on the other -- and a MISSING row and a PENDING one must not be the same thing,
        # because "we have not looked" is an answer the grid has to be able to give.
        for d in grid.get("document_ids") or ():
            for col in grid.get("columns") or ():
                key = (d, col["name"])
                cells.setdefault(key, _shaped(
                    {"grid_id": gid, "document_id": d, "column_name": col["name"],
                     "state": "PENDING", "value": "", "quote": "",
                     "reason": "queued; this cell has not been run yet"},
                    GRID_CELL_KEYS))
        return dict(self.grids[gid])

    def read_grid(self, grid_id: str) -> dict | None:
        row = self.grids.get(grid_id)
        return dict(row) if row else None

    def read_grid_cells(self, grid_id: str) -> list[dict]:
        return [dict(r) for r in self.grid_cells.get(grid_id, {}).values()]

    def list_grids(self, *, limit: int, before_created_at: str | None = None,
                   before_grid_id: str | None = None) -> list[dict]:
        """Newest first, metadata and counts only: no question text, no cell values."""
        _check_grid_page(limit, before_created_at, before_grid_id)
        rows = []
        for gid, g in self.grids.items():
            if before_created_at is not None and (g["created_at"], gid) >= (
                    before_created_at, before_grid_id):
                continue
            cells = list(self.grid_cells.get(gid, {}).values())
            rows.append(_grid_summary(g, columns=len(g["columns"]),
                                      documents=len(g["document_ids"]), cells=len(cells),
                                      pending=sum(c["state"] == "PENDING" for c in cells)))
        return sorted(rows, key=lambda r: (r["created_at"], r["grid_id"]),
                      reverse=True)[:limit]

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

    def write_grid_cell(self, cell: dict, *, if_pending: bool = True) -> bool:
        """True when written. False when a terminal cell already exists for that key.

        `if_pending` is the exactly-once half that lives in code: the key is the primary
        key in Postgres, and refusing to overwrite a terminal cell is what makes a resumed
        worker harmless rather than destructive.
        """
        gid = cell["grid_id"]
        if gid not in self.grids:
            raise StoreError(f"no review grid {gid!r} to write a cell to")
        # 011's two CHECKs, restated here so the dict refuses exactly what Postgres does.
        # Without this the memory backend accepts a FOUND cell with a three-character
        # quote and the gate never sees the divergence.
        state = cell.get("state")
        value, quote = (cell.get("value") or ""), (cell.get("quote") or "")
        reason = cell.get("reason") or ""
        if state == "FOUND":
            if not value.strip() or len(quote.strip()) < 8:
                raise StoreError(
                    f"a FOUND cell needs a value and a quote of at least 8 characters "
                    f"(011 review_grid_cells_found_has_quote); got value={value!r} "
                    f"quote={quote[:12]!r}")
        else:
            if value.strip() or quote.strip() or len(reason.strip()) < 10:
                raise StoreError(
                    f"a {state} cell carries no value and no quote and must say WHY in at "
                    f"least 10 characters (011 review_grid_cells_other_has_reason)")
        # 013's three CHECKs, restated for the same reason as 011's: a rule only Postgres
        # enforces is a rule the gate never runs.
        cost, note = cell.get("cost_inr"), cell.get("cost_note")
        if cost is not None and float(cost) < 0:
            raise StoreError(
                f"a cell cost cannot be negative (013 "
                f"review_grid_cells_cost_not_negative); got {cost!r}")
        if cell.get("provider") in ("azure", "anthropic") and cost is not None \
                and float(cost) == 0:
            raise StoreError(
                f"provider {cell['provider']!r} is BILLED, so 0.00 is a claim the call was "
                f"free (013 review_grid_cells_billed_never_zero). UNPRICED is NULL with a "
                f"note, not zero")
        if state != "PENDING" and cost is None and not note:
            raise StoreError(
                f"a {state} cell has run, so it carries a cost or says why there is none "
                f"(013 review_grid_cells_ran_has_cost_note)")
        key = (cell["document_id"], cell["column_name"])
        cells = self.grid_cells.setdefault(gid, {})
        existing = cells.get(key)
        if if_pending and existing is not None and existing.get("state") != "PENDING":
            return False
        cells[key] = _shaped(cell, GRID_CELL_KEYS)
        return True

    def cancel_grid(self, grid_id: str) -> bool:
        row = self.grids.get(grid_id)
        if row is None:
            return False
        # Marked, never emptied: cancel stops scheduling and keeps every answered cell.
        row["cancelled_at"] = "cancelled"
        return True

    # ── O9: the answer cache ─────────────────────────────────────────────────
    def write_cache_entry(self, entry: dict) -> bool:
        """Upsert by lookup_key. True when written.

        014's CHECK restated: an entry that cites nothing is refused. `servable` could
        never serve such a row, so writing it would create a row whose only possible use
        is to be rejected.
        """
        key = str(entry.get("lookup_key") or "")
        if not key:
            raise StoreError("a cache entry needs a lookup_key")
        if not (entry.get("citations") or []):
            raise StoreError(
                "a cache entry with NO citations is refused (014 "
                "answer_cache.citations): an answer that cites nothing can never be shown "
                "to be still true, so it could only ever be refused on read")
        row = _shaped(entry, CACHE_KEYS)
        row["served"] = int(entry.get("served") or 0)
        self.cache[key] = row
        return True

    def read_cache_entry(self, lookup_key: str) -> dict | None:
        row = self.cache.get(str(lookup_key or ""))
        return dict(row) if row else None

    def bump_cache_stat(self, kind: str, *, day: str) -> None:
        if kind not in CACHE_STATS:
            raise StoreError(f"{kind!r} is not a cache statistic; one of {CACHE_STATS}")
        bucket = self.cache_stats.setdefault(str(day), {k: 0 for k in CACHE_STATS})
        bucket[kind] += 1

    def read_cache_stats(self) -> dict:
        out = {k: 0 for k in CACHE_STATS}
        for bucket in self.cache_stats.values():
            for k in CACHE_STATS:
                out[k] += int(bucket.get(k) or 0)
        return out

    # ── C2: the chat layer ───────────────────────────────────────────────────
    def write_conversation(self, conversation: dict) -> dict:
        cid = conversation["conversation_id"]
        row = {k: conversation.get(k) for k in CONVERSATION_KEYS}
        row["conversation_id"] = cid
        self.conversations[cid] = row
        self.messages.setdefault(cid, [])
        return dict(row)

    def read_conversation(self, conversation_id: str) -> dict | None:
        row = self.conversations.get(conversation_id)
        return dict(row) if row else None

    def list_conversations(self, *, matter_id: str, limit: int = 50) -> list[dict]:
        """One matter's conversations. `matter_id` is REQUIRED -- see `_matter_scope`."""
        want = _matter_scope(matter_id)
        rows = [r for r in self.conversations.values()
                if str(r.get("matter_id") or "") == want]
        rows.sort(key=lambda r: (r.get("updated_at") or "", r["conversation_id"]),
                  reverse=True)
        return [dict(r) for r in rows[:limit]]

    def write_matter(self, matter: dict, *, owner: str | None = None) -> dict:
        mid = str(matter.get("matter_id") or "")
        name = str(matter.get("name") or "").strip()
        if not mid:
            raise StoreError("a matter needs a matter_id")
        if not name:
            raise StoreError("a matter needs a name (019 matters.name)")
        for other, row in self.matters.items():
            if other != mid and str(row.get("name") or "").lower() == name.lower():
                raise StoreError(
                    f"{name!r} is already a matter in this tenant (019 "
                    f"matters_tenant_name_idx)")
        row = {"matter_id": mid, "name": name,
               "client_ref": str(matter.get("client_ref") or ""),
               "closed_at": matter.get("closed_at")}
        new = mid not in self.matters
        self.matters[mid] = row
        if new and owner:
            self.memberships.append(_membership(mid, owner, "owner", owner,
                                                "created the matter"))
        return dict(row)

    def list_matters(self) -> list[dict]:
        """Every matter, unfiltered: memory has no RLS. gateway/access filters by actor."""
        return [dict(r) for r in sorted(self.matters.values(),
                                        key=lambda r: r["name"].lower())]

    # ── 028: matter grants ────────────────────────────────────────────────────
    def _active_grant(self, matter_id, actor_id):
        return next((m for m in self.memberships
                     if m["matter_id"] == str(matter_id) and m["actor_id"] == str(actor_id)
                     and m["revoked_at"] is None), None)

    def matter_role(self, matter_id: str, actor_id: str) -> str | None:
        actor = self.actors.get(str(actor_id or ""))
        if actor is not None and actor.get("disabled_at") is not None:
            return None
        grant = self._active_grant(matter_id, actor_id)
        return grant["role"] if grant else None

    def matter_roles(self, actor_id: str) -> dict:
        return {m["matter_id"]: m["role"] for m in self.memberships
                if m["actor_id"] == str(actor_id) and m["revoked_at"] is None}

    def grant_matter_access(self, *, matter_id: str, actor_id: str, role: str,
                            granted_by: str, reason: str) -> dict:
        _check_grant(role, reason)
        if str(matter_id) not in self.matters:
            raise StoreError("no such matter")
        prior = self._active_grant(matter_id, actor_id)
        if prior is not None and prior["role"] == role:
            return dict(prior)
        if prior is not None:
            prior.update(revoked_at=_utcnow(), revoked_by=str(granted_by),
                         revoke_reason=f"role changed to {role}: {reason}")
        row = _membership(matter_id, actor_id, role, granted_by, reason)
        self.memberships.append(row)
        return dict(row)

    def revoke_matter_access(self, *, matter_id: str, actor_id: str, revoked_by: str,
                             reason: str) -> bool:
        if not str(reason or "").strip():
            raise StoreError("a revocation needs a reason (028 matter_memberships)")
        grant = self._active_grant(matter_id, actor_id)
        if grant is None:
            return False
        grant.update(revoked_at=_utcnow(), revoked_by=str(revoked_by),
                     revoke_reason=str(reason))
        return True

    def list_matter_memberships(self, matter_id: str, *, include_revoked: bool = False) -> list[dict]:
        return [dict(m) for m in self.memberships if m["matter_id"] == str(matter_id)
                and (include_revoked or m["revoked_at"] is None)]

    def share_vault_document(self, document_id: str, *, by_actor: str, reason: str,
                             shared: bool = True) -> dict:
        row = self.vault_docs.get(str(document_id or ""))
        if row is None:
            raise StoreError("no such vault document")
        if row.get("matter_id") or row.get("uploaded_by") != str(by_actor):
            raise StoreError("only the uploader shares an unfiled document")
        event = _access_event("vault_document", document_id, "share" if shared else "unshare",
                              by_actor, reason, from_actor=row.get("uploaded_by"))
        row.update(shared_with_firm_at=_utcnow() if shared else None,
                   shared_by=str(by_actor) if shared else None)
        self.access_events.append(event)
        return dict(row)

    def list_unowned(self) -> dict:
        out = {}
        for kind, (attr, _t, idc, owner, name) in REASSIGNABLE.items():
            out[kind] = [{"id": rid, "name": r.get(name) or ""}
                         for rid, r in getattr(self, attr).items()
                         if not r.get("matter_id") and not r.get(owner)
                         and not r.get("deleted_at")]
        return out

    def reassign_work(self, kind: str, resource_id: str, *, by_actor: str, reason: str,
                      to_actor: str | None = None, to_matter: str | None = None) -> dict:
        if kind not in REASSIGNABLE:
            raise StoreError(f"{kind!r} is not reassignable")
        attr, _t, _idc, owner, _name = REASSIGNABLE[kind]
        row = getattr(self, attr).get(str(resource_id or ""))
        if row is None or row.get("matter_id") or row.get(owner):
            raise StoreError(UNOWNED_ONLY)
        if not (to_actor or to_matter):
            raise StoreError("a reassignment names a new owner, a matter, or both")
        if to_matter is not None and str(to_matter) not in self.matters:
            raise StoreError("no such matter")
        event = _access_event(kind, resource_id, "reassign", by_actor, reason,
                              from_actor=row.get(owner), to_actor=to_actor,
                              to_matter=to_matter)
        if to_actor:
            row[owner] = str(to_actor)
        if to_matter:
            row["matter_id"] = str(to_matter)
            if kind == "vault_document":
                row.update(shared_with_firm_at=None, shared_by=None)
        self.access_events.append(event)
        return dict(row)

    # ── V1: the vault ────────────────────────────────────────────────────────
    def write_vault_document(self, doc: dict, *, run: dict | None = None,
                             queue=None, queued: dict | None = None) -> dict:
        """020's CHECKs restated, so the dict refuses exactly what Postgres refuses.

        With `run` and `queue`/`queued`, the document, its run and its ingest job are one
        unit: if the enqueue raises, the document and run are removed again, as Postgres
        rolls the transaction back. A PENDING document with no job is never left behind.
        """
        did = str(doc.get("document_id") or "")
        if not did:
            raise StoreError("a vault document needs a document_id")
        sha = str(doc.get("sha256") or "")
        if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
            raise StoreError("a vault document is keyed by its bytes' sha256")
        if not str(doc.get("name") or "").strip():
            raise StoreError("a vault document needs a name (020 vault_documents.name)")
        state = str(doc.get("state") or "PENDING")
        if state not in VAULT_STATES:
            raise StoreError(f"{state!r} is not a vault state; one of {VAULT_STATES}")
        if doc.get("doc_class") and not str(doc.get("class_reason") or "").strip():
            raise StoreError(
                "a classified document says WHY (020 vault_documents_class_has_reason): a "
                "bare class in a list of twenty thousand is a number nobody can check")
        if state == "DELETED" and doc.get("text_chars") is not None:
            raise StoreError(
                "a DELETED document carries no text (020 "
                "vault_documents_deleted_has_no_text)")
        prior = self.vault_docs.get(did) or {}
        if prior.get("deleted_at"):
            # A late ingest's final write never revives a deleted document (Postgres:
            # the ON CONFLICT ... WHERE deleted_at IS NULL in the same statement).
            return dict(prior)
        # 028. The uploader is fixed at insert, exactly as Postgres never updates it.
        uploaded_by = prior.get("uploaded_by", doc.get("uploaded_by"))
        # Dedupe is per matter, or per uploader while unfiled (028).
        for other, row in self.vault_docs.items():
            if other != did and row.get("sha256") == sha and _same_vault_scope(
                    row, doc.get("matter_id"), uploaded_by):
                raise DuplicateVaultDocument(
                    f"these bytes are already in this vault scope as {other} (028 "
                    f"vault_documents_matter_sha / owner_sha)", document_id=other)
        row = {"document_id": did, "matter_id": doc.get("matter_id"), "sha256": sha,
               "name": str(doc["name"]), "byte_count": int(doc.get("byte_count") or 0),
               "state": state, "doc_class": doc.get("doc_class"),
               "class_reason": doc.get("class_reason"),
               "text_chars": doc.get("text_chars"),
               "ocr_state": str(doc.get("ocr_state") or "NOT_NEEDED"),
               "deleted_at": doc.get("deleted_at"), "uploaded_by": uploaded_by,
               "shared_with_firm_at": prior.get("shared_with_firm_at"),
               "shared_by": prior.get("shared_by"), "failure_reason": None}
        self.vault_docs[did] = row
        if run is not None:
            self.write_run(run)
        if queue is not None and queued is not None:
            try:
                job = queue.enqueue(**queued)
            except Exception:
                if prior:
                    self.vault_docs[did] = prior
                else:
                    self.vault_docs.pop(did, None)
                if run is not None:
                    for table in (self.runs, self.steps, self.props):
                        table.pop(run["id"], None)
                raise
            return {**row, "job_id": job.job_id}
        return dict(row)

    def read_vault_document(self, document_id: str) -> dict | None:
        row = self.vault_docs.get(str(document_id or ""))
        return dict(row) if row else None

    def vault_documents_by_sha256(self, sha256: str) -> list[dict]:
        return [dict(r) for r in self.vault_docs.values()
                if r.get("sha256") == sha256 and not r.get("deleted_at")]

    def list_vault_documents(self, *, matter_id: str) -> list[dict]:
        """One matter's documents. 8b: there is no cross-matter listing."""
        want = _matter_scope(matter_id)
        return [dict(r) for r in sorted(self.vault_docs.values(),
                                        key=lambda r: r["name"].lower())
                if str(r.get("matter_id") or "") == want and not r.get("deleted_at")]

    def browse_vault_documents(self, *, matter_id: str | None, query: str, limit: int, offset: int) -> list[dict]:
        """Metadata for one matter, or unfiled rows only; never all matters."""
        rows = sorted((r for r in self.vault_docs.values()
                       if r.get("matter_id") == matter_id and not r.get("deleted_at")
                       and r.get("state") != "DELETED" and query.lower() in r["name"].lower()),
                      key=lambda r: (r["name"].lower(), r["document_id"]))
        fields = ("document_id", "sha256", "name", "state", "matter_id", "byte_count", "doc_class",
                  "uploaded_by", "shared_with_firm_at")
        return [{k: r.get(k) for k in fields} for r in rows[offset:offset + limit]]

    def write_vault_chunks(self, document_id: str, chunks: list) -> int:
        did = str(document_id or "")
        if did not in self.vault_docs:
            raise StoreError(f"no vault document {did!r} to chunk")
        if self.vault_docs[did].get("deleted_at"):
            return 0
        rows = []
        for i, text in enumerate(chunks or ()):
            if not str(text or "").strip():
                raise StoreError(f"chunk {i} is empty (020 vault_chunks.text)")
            rows.append({"document_id": did, "ordinal": i, "text": str(text)})
        self.vault_chunks[did] = rows
        return len(rows)

    def read_vault_chunks(self) -> list[dict]:
        """Every live chunk in this tenant, with its document's name and class.

        Tenant-wide on purpose: V1 specifies BM25 PER TENANT, and a vault whose search
        stopped at a matter boundary could not answer "have we ever agreed to this".
        Listing is matter-scoped (8b); searching is not, and the result says which.
        """
        out = []
        for did, rows in self.vault_chunks.items():
            doc = self.vault_docs.get(did) or {}
            if doc.get("deleted_at"):
                continue
            for r in rows:
                out.append(dict(r, name=doc.get("name") or "",
                                doc_class=doc.get("doc_class") or "",
                                matter_id=doc.get("matter_id"),
                                uploaded_by=doc.get("uploaded_by"),
                                shared_with_firm_at=doc.get("shared_with_firm_at")))
        return out

    def write_vault_tags(self, document_id: str, tags: list) -> int:
        did = str(document_id or "")
        if did not in self.vault_docs:
            raise StoreError(f"no vault document {did!r} to tag")
        if self.vault_docs[did].get("deleted_at"):
            return 0
        rows = []
        for t in tags or ():
            quote = str((t or {}).get("quote") or "")
            if len(quote.strip()) < 8:
                raise StoreError(
                    "a tag carries a quote of at least 8 characters (020 "
                    "vault_tags.quote): a tag with no span is an assertion about a "
                    "document nobody can check against it")
            if not str((t or {}).get("tag") or "").strip():
                raise StoreError("a tag needs a name")
            rows.append({"document_id": did, "tag": str(t["tag"]), "quote": quote,
                         "span_start": t.get("span_start"),
                         "span_end": t.get("span_end")})
        self.vault_tags[did] = rows
        return len(rows)

    def read_vault_tags(self, document_id: str) -> list[dict]:
        return [dict(r) for r in self.vault_tags.get(str(document_id or ""), [])]

    def delete_vault_document(self, document_id: str, *, now: str) -> bool:
        """The ROW survives; the text and the chunks do not.

        "We never had it" and "we had it and destroyed it on 4 March" are different
        answers to a regulator, and only one of them is true.
        """
        row = self.vault_docs.get(str(document_id or ""))
        if row is None or row.get("deleted_at"):
            return False
        row["state"] = "DELETED"
        row["deleted_at"] = str(now)
        row["text_chars"] = None
        row["failure_reason"] = None
        self.vault_chunks.pop(str(document_id), None)
        self.vault_tags.pop(str(document_id), None)
        return True

    def fail_vault_document(self, document_id: str, reason: str) -> bool:
        """PENDING -> FAILED with the reason (030). Only a PENDING document moves."""
        if not str(reason or "").strip():
            raise StoreError("a FAILED document says why (030 vault_documents_failed_has_reason)")
        row = self.vault_docs.get(str(document_id or ""))
        if row is None or row.get("state") != "PENDING":
            return False
        row["state"], row["failure_reason"] = "FAILED", str(reason)
        return True

    def retry_vault_document(self, document_id: str, *, queue) -> bool:
        """FAILED -> PENDING, its run back to PLANNED and its DEAD job requeued, as one unit.

        False when the document is not FAILED (already retried, or never failed), so two
        retries cannot both requeue. If the requeue raises, nothing has changed.
        """
        did = str(document_id or "")
        row = self.vault_docs.get(did)
        if row is None or row.get("state") != "FAILED":
            return False
        if (self.runs.get(did) or {}).get("status") != "FAILED":
            raise RetryConflict("this document's run is not FAILED, so it was not retried")
        prior_doc, prior_run = dict(row), dict(self.runs[did])
        prior_steps = list(self.steps.get(did) or [])
        row["state"], row["failure_reason"] = "PENDING", None
        self.runs[did].update(status="PLANNED", refusal_code=None, result=None)
        self.steps[did] = []
        try:
            queue.requeue_dead(did)
        except Exception:
            self.vault_docs[did] = prior_doc
            self.runs[did] = prior_run
            self.steps[did] = prior_steps
            raise
        return True

    # ── T3 move 10: document_checks (023) ───────────────────────────────────
    # 023's CHECKs restated, so the dict refuses exactly what Postgres refuses. The gate runs
    # against MemoryBackend far more often than against a database, and a rule only Postgres
    # enforces is a rule the gate never runs -- `write_run`'s own lesson, learned when a
    # REFUSED row with no code passed the gate and failed on the live server.
    def write_document_check(self, check: dict) -> dict:
        from checker import doc_validity as _dval
        from checker import doc_verification as _dver
        vs = str(check.get("verification_status") or "")
        st = str(check.get("validity_status") or "")
        action = str(check.get("action") or "")
        reason = str(check.get("action_reason") or "")
        if vs not in (_dver.COMPLETE, _dver.INCOMPLETE, _dver.FAILED):
            raise StoreError(f"{vs!r} is not a verification status (023 CHECK)")
        if st not in _dval.STATUSES:
            raise StoreError(f"{st!r} is not a validity status (023 CHECK)")
        if action not in _dval.ACTIONS:
            raise StoreError(f"{action!r} is not an action (023 CHECK)")
        if len(reason.strip()) < 20:
            raise StoreError(
                "an action needs a reason of at least 20 characters (023 "
                "action_reason): an action with no reason is a verdict nobody can check, "
                "and this row is read months later by someone who was not here")
        if (action == _dval.RENEW_BY) != bool(check.get("renew_by")):
            raise StoreError(
                f"renew_by is present exactly when the action is RENEW_BY (023 "
                f"document_checks_renew_by_iff_renew): action={action!r}, "
                f"renew_by={check.get('renew_by')!r}. A RENEW_BY with no date is a deadline "
                f"the calendar cannot show; a date on a KEEP is one that would appear for a "
                f"document needing nothing")
        if action == _dval.KEEP and (st not in _dval.IN_FORCE or vs == _dver.FAILED):
            raise StoreError(
                f"KEEP requires a document in force whose verification did not fail (023 "
                f"document_checks_keep_requires_force): validity={st!r}, "
                f"verification={vs!r}")
        row = dict(check)
        row["law_versions"] = _copied(check.get("law_versions"))
        self.document_checks.append(row)
        return dict(row)

    def read_document_checks(self, *, document_id: str = "",
                             limit: int = 100) -> list[dict]:
        rows = [dict(r) for r in self.document_checks
                if not document_id or r.get("document_id") == document_id]
        rows.sort(key=lambda r: str(r.get("checked_at") or ""), reverse=True)
        return rows[:limit]

    def read_renewals(self, *, on_or_before: str = "") -> list[dict]:
        """Outstanding RENEW_BY rows, soonest first. The calendar's input.

        Only the LATEST check per document counts. A document checked in March (RENEW_BY) and
        again in April (KEEP, because it was renewed) must not still show a deadline. That is
        the cost of the append-only shape, and the reason this is not a bare
        `WHERE renew_by IS NOT NULL`.
        """
        latest: dict = {}
        for r in sorted(self.document_checks,
                        key=lambda x: str(x.get("checked_at") or "")):
            latest[r.get("document_id")] = r
        out = [dict(r) for r in latest.values() if r.get("renew_by")
               and (not on_or_before or str(r["renew_by"]) <= on_or_before)]
        out.sort(key=lambda r: str(r.get("renew_by")))
        return out

    def vault_counts(self) -> dict:
        live = [r for r in self.vault_docs.values() if not r.get("deleted_at")]
        by_state: dict = {}
        for r in live:
            by_state[r["state"]] = by_state.get(r["state"], 0) + 1
        return {"documents": len(live), "by_state": by_state,
                "deleted": len(self.vault_docs) - len(live),
                "unsearchable": sum(1 for r in live
                                    if r["state"] in ("PENDING", "CANNOT_READ", "FAILED"))}

    def find_turn(self, request_id: str, payload_digest: str) -> dict | None:
        with self._turn_lock:
            prior = self.turn_requests.get(request_id)
            if prior is None:
                return None
            if prior["digest"] != payload_digest:
                raise TurnConflict("request_id was already used with different input")
            return next((deepcopy(m) for m in self.messages[prior["conversation_id"]]
                         if m["message_id"] == prior["message_id"]), None)

    def reserve_turn(self, conversation: dict, user: dict, assistant: dict, *,
                     request_id: str, payload_digest: str, queue=None, queued=None) -> tuple[dict, bool]:
        """Reserve adjacent user/assistant slots and the retry key under one lock."""
        with self._turn_lock, (queue._lock if queued is not None else nullcontext()):
            prior = self.find_turn(request_id, payload_digest)
            if prior is not None:
                return prior, False
            cid = conversation["conversation_id"]
            existing = self.conversations.get(cid)
            if existing and existing.get("matter_id") != conversation.get("matter_id"):
                raise TurnConflict("a conversation's matter cannot change during a turn")
            ordinal = max((m["ordinal"] for m in self.messages.get(cid, [])), default=-1) + 1
            u = dict(user, conversation_id=cid, ordinal=ordinal)
            a = dict(assistant, conversation_id=cid, ordinal=ordinal + 1)
            _check_message(u)
            _check_message(a)
            previous = list(self.messages.get(cid, []))
            try:
                if existing is None:
                    self.write_conversation(conversation)
                if queued is not None:
                    self.write_run({"id": queued["run_id"], "intent": queued["intent"],
                                    "status": "PLANNED", "refusal_code": None,
                                    "steps": [], "propositions": []})
                self.append_message(u)
                row = self.append_message(a)
                if queued is not None:
                    queue.enqueue(**queued)
            except Exception:
                if existing is None:
                    self.conversations.pop(cid, None)
                    self.messages.pop(cid, None)
                else:
                    self.messages[cid] = previous
                if queued is not None:
                    for collection in (self.runs, self.steps, self.props):
                        collection.pop(queued["run_id"], None)
                raise
            self.turn_requests[request_id] = {"digest": payload_digest,
                "conversation_id": cid, "message_id": a["message_id"]}
            return row, True

    def expire_pending_message(self, message_id: str, envelope: dict) -> bool:
        with self._turn_lock:
            for thread in self.messages.values():
                for m in thread:
                    if (m["message_id"] == message_id and m["role"] == "assistant"
                            and m.get("envelope") is None and m.get("run_id") is None):
                        m["envelope"] = deepcopy(envelope)
                        return True
            return False

    def update_message(self, message_id: str, *, task, run_id, envelope, metadata) -> bool:
        with self._turn_lock:
            for thread in self.messages.values():
                for m in thread:
                    if m["message_id"] == message_id and m["role"] == "assistant":
                        m.update(task=task, run_id=run_id, envelope=deepcopy(envelope),
                                 metadata=deepcopy(metadata))
                        return True
            return False

    def append_message(self, message: dict) -> dict:
        _check_message(message)
        cid = message["conversation_id"]
        if cid not in self.conversations:
            raise StoreError(f"no conversation {cid!r} to append to")
        thread = self.messages.setdefault(cid, [])
        if any(m["ordinal"] == message["ordinal"] for m in thread):
            # The UNIQUE (conversation_id, ordinal) constraint in 010, enforced here too so
            # the two backends refuse the same row rather than one of them accepting it.
            raise StoreError(f"ordinal {message['ordinal']} is already used in {cid!r}")
        row = _shaped(message, MESSAGE_KEYS)
        row["file_ids"] = list(message.get("file_ids") or [])
        row["metadata"] = deepcopy(message.get("metadata"))
        thread.append(row)
        return deepcopy(row)

    def read_messages(self, conversation_id: str) -> list[dict]:
        return [deepcopy(m) for m in sorted(self.messages.get(conversation_id, []),
                                        key=lambda m: m["ordinal"])]

    def set_message_envelope(self, message_id: str, envelope: dict) -> bool:
        for thread in self.messages.values():
            for m in thread:
                if m["message_id"] == message_id:
                    if m["role"] != "assistant":
                        raise MessageShape("only an assistant message carries an envelope")
                    m["envelope"] = dict(envelope)
                    return True
        return False

    def next_ordinal(self, conversation_id: str) -> int:
        return len(self.messages.get(conversation_id, []))

    def write_run(self, run: dict) -> None:
        rid = run["id"]
        # 002's runs_refusal_code_iff_refused, restated. Postgres refuses a REFUSED run
        # with no code and the dict accepted one, so a test row that could never exist in
        # production passed the gate and failed on the live server -- a rule only Postgres
        # enforces is a rule the gate never runs.
        status, code = str(run.get("status") or ""), run.get("refusal_code")
        if status == "REFUSED" and not str(code or "").strip():
            raise StoreError(
                "a REFUSED run must carry a refusal_code (002 "
                "runs_refusal_code_iff_refused): a refusal with no nameable reason is "
                "indistinguishable from a failure")
        if status != "REFUSED" and str(code or "").strip():
            raise StoreError(
                f"only a REFUSED run carries a refusal_code (002 "
                f"runs_refusal_code_iff_refused); status={status!r} has {code!r}")
        self.runs[rid] = {k: v for k, v in run.items()
                          if k not in ("steps", "propositions")}
        # Postgres returns the column whether or not it was written; so does this.
        self.runs[rid]["law_versions"] = _copied(run.get("law_versions"))
        # 016. Recorded at write time from checker/critic.enabled(), because a setting read
        # per call leaves no trace of itself -- and the critic's success case is INVISIBLE:
        # "found nothing" and "was off" are the same clean answer afterwards.
        self.runs[rid]["critic_enabled"] = _critic_enabled_now()
        # 017. Supplied by the caller that has the sentence counts; NULL when the path
        # produced no entailment verdict to count. Never derived here from TRACED alone,
        # which would be a different measurement under the same name.
        self.runs[rid]["nonconformity"] = run.get("nonconformity")
        self.runs[rid]["nonconformity_note"] = run.get("nonconformity_note")
        self.steps[rid] = [_shaped(s, STEP_KEYS) for s in run.get("steps", [])]
        self.props[rid] = [_shaped(p, PROPOSITION_KEYS)
                           for p in run.get("propositions", [])]

    def read_run(self, run_id: str) -> dict | None:
        if run_id not in self.runs:
            return None
        out = dict(self.runs[run_id])
        out.setdefault("result", None)
        out["steps"] = [dict(s) for s in self.steps.get(run_id, [])]
        out["propositions"] = [dict(p) for p in self.props.get(run_id, [])]
        return out

    def put_document(self, *, sha256: str, name: str, byte_count: int) -> dict:
        row = {"sha256": sha256, "name": name, "byte_count": byte_count,
               "tenant_id": self.tenant_id}
        self.documents[sha256] = row
        return dict(row)

    def get_document(self, sha256: str) -> dict | None:
        row = self.documents.get(sha256)
        return dict(row) if row else None

    def write_decision(self, decision: dict) -> dict:
        rid = decision["run_id"]
        existing = self.decisions.setdefault(rid, [])
        # The UNIQUE (run_id, item_ref) of 005, enforced here too so the two backends
        # refuse the same second decision rather than one of them silently keeping both.
        if any(d["item_ref"] == decision["item_ref"] for d in existing):
            raise DecisionExists(
                f"{decision['item_ref']} on run {rid} already has a decision. A reviewer "
                f"changing their mind writes a new one against a new run; overwriting "
                f"would destroy the label, which is the point of storing it.")
        row = _shaped(decision, DECISION_KEYS)
        if not row.get("decided_at"):
            # Postgres defaults this column; without the same default here one backend
            # returns a timestamp and the other returns None for an identical write.
            from datetime import datetime, timezone
            row["decided_at"] = datetime.now(timezone.utc).isoformat()
        existing.append(row)
        return dict(row)

    def read_decisions(self, run_id: str) -> list[dict]:
        return [dict(d) for d in self.decisions.get(run_id, [])]

    def append_step(self, run_id: str, step: dict, *, key: str) -> bool:
        """Append one step unless `key` was already written. True if it was written now.

        The return value matters: a worker that cannot tell "I wrote this" from "this was
        already there" cannot tell a resumed run from a fresh one, and would re-bill.
        """
        rows = self.steps.setdefault(run_id, [])
        if any(r.get("idempotency_key") == key for r in rows):
            return False
        rows.append({**_shaped(step, STEP_KEYS), "idempotency_key": key})
        return True

    def write_cascade(self, record: dict, *, run_id: str | None = None) -> dict:
        """Store one `model_cascade.Result.to_dict()`. Returns the row as it reads back."""
        import uuid as _uuid
        row = {
            "cascade_id": record.get("cascade_id") or str(_uuid.uuid4()),
            "run_id": run_id,
            "status": record.get("status", ""),
            "error": record.get("error"),
            "attempts": [dict(a) for a in record.get("attempts", [])],
            "body_ids": list(record.get("body_ids", [])),
            "claim_count": len(record.get("claims", [])),
            "refusal_count": len(record.get("refusals", [])),
            "total_cost_inr": record.get("total_cost_inr"),
        }
        _check_cascade(row)
        self.cascades.append(row)
        return dict(row)

    def read_cascades(self, *, run_id: str | None = None, limit: int = 1000) -> list[dict]:
        rows = [c for c in self.cascades if run_id is None or c["run_id"] == run_id]
        return [dict(c) for c in rows[:limit]]

    def set_run(self, run_id: str, *, status: str, refusal_code=None, result=None) -> None:
        row = self.runs.setdefault(run_id, {"id": run_id})
        row["status"] = status
        row["refusal_code"] = refusal_code
        if result is not None:
            row["result"] = result
        cat, why = failure_tag(status, refusal_code,
                               result if result is not None else row.get("result"))
        row["failure_category"], row["failure_reason"] = cat, why

    def set_run_progress(self, run_id: str, progress: dict) -> None:
        row = self.runs.get(run_id)
        if row is not None and row.get("status") == "RUNNING":
            row["progress"] = dict(progress)

    def read_run_progress(self, run_id: str) -> dict | None:
        row = self.runs.get(run_id)
        return dict(row["progress"]) if row and row.get("progress") else None

    # ── 8a: users, roles and invites ─────────────────────────────────────────
    def write_actor(self, actor: dict) -> dict:
        """Create or update a user. 018's CHECKs restated, so the dict refuses what
        Postgres refuses."""
        from gateway.roles import ROLES
        aid = str(actor.get("actor_id") or "")
        if not aid:
            raise StoreError("an actor needs an actor_id")
        role = str(actor.get("role") or "viewer")
        if role not in ROLES:
            raise StoreError(
                f"{role!r} is not a role (018 actors_role_known); one of {ROLES}")
        pw = actor.get("password_hash")
        if pw is not None and not str(pw).startswith("scrypt$"):
            raise StoreError(
                "a password hash is scrypt in its self-describing form, or nothing (018 "
                "actors_password_is_scrypt). A bare digest would accept a SHA-256 of a "
                "password, which gateway/passwords.py exists to make impossible")
        email = str(actor.get("email") or "").strip() or None
        if email:
            for other, row in self.actors.items():
                if other != aid and str(row.get("email") or "").lower() == email.lower():
                    raise StoreError(
                        f"{email!r} already has an account in this tenant (018 "
                        f"actors_tenant_email_idx)")
        from datetime import datetime, timezone
        joined = (self.actors.get(aid) or {}).get("created_at") or \
            datetime.now(timezone.utc).isoformat()
        row = {"actor_id": aid, "label": str(actor.get("label") or ""), "role": role,
               "email": email, "password_hash": pw,
               "disabled_at": actor.get("disabled_at"), "created_at": joined}
        self.actors[aid] = row
        return dict(row)

    def read_actor(self, actor_id: str) -> dict | None:
        row = self.actors.get(str(actor_id or ""))
        return dict(row) if row else None

    def create_invite(self, invite: dict) -> dict:
        """One LIVE invite per email per tenant, as 018's partial unique index says."""
        from gateway.roles import ROLES
        email = str(invite.get("email") or "").strip()
        if "@" not in email[1:]:
            raise StoreError(f"{email!r} is not an email address")
        if str(invite.get("role") or "") not in ROLES:
            raise StoreError(f"an invite needs a real role; one of {ROLES}")
        th = str(invite.get("token_hash") or "")
        if len(th) != 64 or any(c not in "0123456789abcdef" for c in th):
            raise StoreError("an invite stores the sha256 of its token, never the token")
        if not str(invite.get("expires_at") or "").strip():
            raise StoreError(
                "an invite must expire. One with no horizon is a credential, and a "
                "credential sitting in an inbox for a year is the one that gets used by "
                "whoever buys the laptop")
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        for row in self.invites.values():
            if row.get("accepted_at") is None and row.get("cancelled_at") is None and \
                    str(row.get("email") or "").lower() == email.lower():
                if _when(row["expires_at"]) <= now:
                    # An expired invite is retired by the new one, as on Postgres.
                    row["cancelled_at"] = now.isoformat()
                    row["cancelled_by"] = str(invite.get("invited_by") or "")
                    continue
                raise StoreError(
                    f"{email!r} already has a live invite (036 invites_live_per_email_idx)")
        row = {"invite_id": str(invite.get("invite_id") or ""), "email": email,
               "role": invite["role"], "token_hash": th,
               "invited_by": str(invite.get("invited_by") or ""),
               "created_at": now.isoformat(),
               "expires_at": str(invite["expires_at"]),
               "accepted_at": None, "accepted_by": None,
               "cancelled_at": None, "cancelled_by": None}
        self.invites[row["invite_id"]] = row
        return dict(row)

    def accept_invite(self, token_hash: str, *, actor_id: str, now: str,
                      actor: dict | None = None) -> dict | None:
        """Mark an invite used, ONCE. Returns the invite, or None if it cannot be used.

        `actor`, when given, is the account the invite creates. It is written only if the
        invite is spent, so a refused accept leaves no account behind.

        None covers three different situations deliberately -- unknown token, already
        accepted, expired -- because telling them apart at this boundary is how a token is
        probed. The caller gets one answer: this token does not let you in.
        """
        for row in self.invites.values():
            if row.get("token_hash") != str(token_hash or ""):
                continue
            if row.get("accepted_at") is not None:
                return None                      # single use, and it is already used
            if row.get("cancelled_at") is not None:
                return None                      # an admin withdrew it (036)
            if str(row.get("expires_at") or "") <= str(now):
                return None
            if actor is not None:
                self.write_actor(dict(actor, actor_id=str(actor_id)))
            row["accepted_at"] = str(now)
            row["accepted_by"] = str(actor_id)
            return dict(row)
        return None

    def find_actor_by_email(self, email: str) -> dict | None:
        """The account with this email in this tenant, case-insensitively, or None."""
        want = str(email or "").strip().lower()
        if not want:
            return None
        for row in self.actors.values():
            if str(row.get("email") or "").lower() == want:
                return dict(row)
        return None

    def read_invite(self, token_hash: str) -> dict | None:
        """The invite stored under this token hash, used or not; the caller judges it."""
        for row in self.invites.values():
            if row.get("token_hash") == str(token_hash or ""):
                return dict(row)
        return None

    def list_actors(self) -> list[dict]:
        """Every person with an email, without their password hash."""
        return [{k: v for k, v in row.items() if k != "password_hash"}
                for row in sorted(self.actors.values(),
                                  key=lambda r: str(r.get("email") or "").lower())
                if row.get("email")]

    def list_pending_invites(self) -> list[dict]:
        """Invites still usable: not accepted, not cancelled, not expired. Newest first.
        Never the token hash."""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        rows = [r for r in self.invites.values()
                if r.get("accepted_at") is None and r.get("cancelled_at") is None
                and _when(r["expires_at"]) > now]
        rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
        return [{k: r.get(k) for k in _PENDING_INVITE_COLS} for r in rows]

    def cancel_invite(self, invite_id: str, *, cancelled_by: str) -> bool:
        """Withdraw an unused invite. The row stays, marked. False if there is no such
        unused invite in this tenant."""
        from datetime import datetime, timezone
        row = self.invites.get(str(invite_id or ""))
        if row is None or row.get("accepted_at") is not None \
                or row.get("cancelled_at") is not None:
            return False
        row["cancelled_at"] = datetime.now(timezone.utc).isoformat()
        row["cancelled_by"] = str(cancelled_by)
        return True

    def create_session(self, session: dict) -> dict:
        """026's CHECKs, restated: the hash is sha256-shaped, and it expires."""
        th = str(session.get("token_hash") or "")
        if len(th) != 64 or any(c not in "0123456789abcdef" for c in th):
            raise StoreError("a session stores the sha256 of its token, never the token "
                             "(026 sessions_token_hash_idx)")
        if not str(session.get("expires_at") or "").strip():
            raise StoreError("a session must expire (026 sessions_expires_after_creation)")
        sid = str(session.get("session_id") or "")
        row = {"session_id": sid, "actor_id": str(session.get("actor_id") or ""),
               "token_hash": th, "expires_at": str(session["expires_at"]),
               "revoked_at": None}
        self.sessions[sid] = row
        return dict(row)

    def revoke_session(self, token_hash: str) -> bool:
        """True if a LIVE session held this hash and is now revoked; False otherwise.

        Scoped by whatever the caller already knows: in practice this is always called
        through a backend bound to one tenant, over a dict with no tenant filter of its
        own -- MemoryBackend has none, by design (see backend_for in gateway/app.py).
        """
        from datetime import datetime, timezone
        for row in self.sessions.values():
            if row.get("token_hash") == str(token_hash or "") and row.get("revoked_at") is None:
                row["revoked_at"] = datetime.now(timezone.utc).isoformat()
                return True
        return False

    def read_labels(self) -> list[dict]:
        """[{task, body, decision}] — every lawyer decision, with the run's intent.

        CAL-1's input. `body` is read from the run's result when it recorded one; a
        decision whose run named no body comes back with body "" rather than being
        dropped, because "we have 40 labels and cannot tell which law they are about" is
        a different problem from "we have no labels".
        """
        out = []
        for run_id, rows in self.decisions.items():
            run = self.runs.get(run_id) or {}
            result = run.get("result") if isinstance(run.get("result"), dict) else {}
            bodies = [str(b.get("body") or "") for b in (result.get("bodies") or ())
                      if isinstance(b, dict)]
            for row in rows:
                out.append({"task": str(run.get("intent") or ""),
                            "body": bodies[0] if bodies else "",
                            "decision": str(row.get("decision") or "")})
        return out

    def read_failure_counts(self) -> list[dict]:
        """[{week, category, count}] over every tagged run. Untagged runs are their OWN
        row (category None), never dropped: excluding them would shrink the denominator
        and make the tagged failures look like the whole picture."""
        buckets: dict = {}
        for row in self.runs.values():
            if str(row.get("status") or "").upper() == "ANSWERED":
                continue
            week = str(row.get("finished_at") or row.get("created_at") or "")[:10] or None
            key = (week, row.get("failure_category"))
            buckets[key] = buckets.get(key, 0) + 1
        return [{"week": w, "category": c, "count": n}
                for (w, c), n in sorted(buckets.items(), key=lambda kv: (str(kv[0][0]),
                                                                        str(kv[0][1])))]

    # The shape agents/runtime.Store expects, so a run can be executed straight onto it.
    def read(self, run_id: str) -> dict | None:
        return self.read_run(run_id)

    def write(self, run: dict) -> None:
        self.write_run(run)
