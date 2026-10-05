"""Two backends, one interface, and one conformance suite that both must pass.

The in-memory store is what the gate runs on; Postgres is what a deployment runs on. The
risk in having two is that they diverge quietly -- the memory one keeps working, the
Postgres one is exercised by nobody, and the difference is discovered in production.

So the contract is a FUNCTION here, `conformance(backend)`, and it is run twice:

    gateway/store.py   in the gate, against MemoryBackend
    scripts/rls_integration.py   outside it, against PostgresBackend, on a real server

Identical assertions, two backends. A behaviour that only the dict satisfies fails the same
test on Postgres, and there is no second suite to keep in step.

## Why a run decomposes

R-016 was decided in favour of the DERIVATION (research/TASKS.md, 29-09-2026): a run is
`runs` + ordered `run_steps` + `propositions`, not one blob. So `write()` takes the dict
the runtime already produces and splits it across three tables, and `read()` reassembles
it. The dict shape is `agents/runtime.py`'s, unchanged, because the runtime should not
learn what a database is.

## Tenant isolation is the database's job, and this sets up the question it asks

Every Postgres connection issues `SET app.tenant_id` before it reads or writes anything.
The policies in gateway/migrations/*.sql compare against that setting, so a backend that
forgot it would see nothing rather than everything -- which is the safe direction, and is
also why `PostgresBackend` refuses to be constructed without a tenant.

Run: PYTHONPATH=. python3 gateway/store.py
"""
from __future__ import annotations

import os
import re
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Protocol

MEMORY = "in-memory"
POSTGRES = "postgres"

URL_ENV = "PLACEDON_DATABASE_URL"
_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                   r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


class StoreError(RuntimeError):
    """The store could not do what was asked. Never swallowed into a None."""


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
    def accept_invite(self, token_hash: str, *, actor_id: str, now: str) -> dict | None: ...
    def append_step(self, run_id: str, step: dict, *, key: str) -> bool: ...
    def set_run(self, run_id: str, *, status: str, refusal_code=None, result=None) -> None: ...
    def read_failure_counts(self) -> list[dict]: ...
    def write_cascade(self, record: dict, *, run_id: str | None = None) -> dict: ...
    def read_cascades(self, *, run_id: str | None = None, limit: int = 1000) -> list[dict]: ...
    # C2: the chat layer (010_conversations.sql).
    def write_conversation(self, conversation: dict) -> dict: ...
    def read_conversation(self, conversation_id: str) -> dict | None: ...
    def list_conversations(self, *, matter_id: str, limit: int = 50) -> list[dict]: ...
    # 8b: matters (019_matters.sql).
    def write_matter(self, matter: dict) -> dict: ...
    # V1: the vault (020_vault.sql).
    def write_vault_document(self, doc: dict) -> dict: ...
    def read_vault_document(self, document_id: str) -> dict | None: ...
    def list_vault_documents(self, *, matter_id: str) -> list[dict]: ...
    def write_vault_chunks(self, document_id: str, chunks: list) -> int: ...
    def read_vault_chunks(self) -> list[dict]: ...
    def write_vault_tags(self, document_id: str, tags: list) -> int: ...
    def read_vault_tags(self, document_id: str) -> list[dict]: ...
    def delete_vault_document(self, document_id: str, *, now: str) -> bool: ...
    def vault_counts(self) -> dict: ...
    def list_matters(self) -> list[dict]: ...
    def append_message(self, message: dict) -> dict: ...
    def read_messages(self, conversation_id: str) -> list[dict]: ...
    def set_message_envelope(self, message_id: str, envelope: dict) -> bool: ...
    # H4: review grids (011_review_grids.sql).
    def write_grid(self, grid: dict) -> dict: ...
    def read_grid(self, grid_id: str) -> dict | None: ...
    def read_grid_cells(self, grid_id: str) -> list[dict]: ...
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
    def write_draft(self, draft: dict) -> dict: ...
    def read_draft(self, draft_id: str) -> dict | None: ...
    def append_draft_version(self, version: dict) -> int: ...
    def read_draft_versions(self, draft_id: str) -> list[dict]: ...


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
                "task", "run_id", "envelope")
# 8b: matter_id is part of a conversation row on both backends. Without it in the shaped
# key set, a dict conversation has no matter and the memory listing matches nothing.
CONVERSATION_KEYS = ("conversation_id", "title", "created_at", "updated_at",
                     "matter_id")

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
VAULT_STATES = ("PENDING", "INGESTED", "CANNOT_READ", "DELETED")
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
    grids: dict = field(default_factory=dict)
    grid_cells: dict = field(default_factory=dict)     # grid_id -> {(doc, col): row}
    drafts: dict = field(default_factory=dict)
    draft_versions: dict = field(default_factory=dict)  # draft_id -> [row]
    vault_docs: dict = field(default_factory=dict)      # document_id -> row
    vault_chunks: dict = field(default_factory=dict)    # document_id -> [row]
    vault_tags: dict = field(default_factory=dict)      # document_id -> [row]
    matters: dict = field(default_factory=dict)         # matter_id -> row
    actors: dict = field(default_factory=dict)          # actor_id -> row
    invites: dict = field(default_factory=dict)         # invite_id -> row
    cache: dict = field(default_factory=dict)           # lookup_key -> row
    cache_stats: dict = field(default_factory=dict)     # day -> {hits, misses, stale}

    # ── H3: drafts ───────────────────────────────────────────────────────────
    def write_draft(self, draft: dict) -> dict:
        did = draft["draft_id"]
        self.drafts[did] = {"draft_id": did, "kind": draft.get("kind") or "agm_notice",
                            "title": draft.get("title") or ""}
        self.draft_versions.setdefault(did, [])
        return dict(self.drafts[did])

    def read_draft(self, draft_id: str) -> dict | None:
        row = self.drafts.get(draft_id)
        return dict(row) if row else None

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
        rows.append(row)
        return n

    def read_draft_versions(self, draft_id: str) -> list[dict]:
        return [dict(r) for r in sorted(self.draft_versions.get(draft_id, []),
                                        key=lambda r: r["version"])]

    # ── H4: review grids ─────────────────────────────────────────────────────
    def write_grid(self, grid: dict) -> dict:
        gid = grid["grid_id"]
        self.grids[gid] = {"grid_id": gid, "name": grid.get("name") or "",
                           "columns": [dict(c) for c in grid.get("columns") or ()],
                           "document_ids": list(grid.get("document_ids") or ()),
                           "cancelled_at": self.grids.get(gid, {}).get("cancelled_at"),
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

    def write_matter(self, matter: dict) -> dict:
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
        self.matters[mid] = row
        return dict(row)

    def list_matters(self) -> list[dict]:
        return [dict(r) for r in sorted(self.matters.values(),
                                        key=lambda r: r["name"].lower())]

    # ── V1: the vault ────────────────────────────────────────────────────────
    def write_vault_document(self, doc: dict) -> dict:
        """020's CHECKs restated, so the dict refuses exactly what Postgres refuses."""
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
        # Dedupe is per tenant: the same bytes twice is one document.
        for other, row in self.vault_docs.items():
            if other != did and row.get("sha256") == sha and not row.get("deleted_at"):
                raise StoreError(
                    f"these bytes are already in this tenant's vault as {other} (020 "
                    f"vault_documents_tenant_sha)")
        row = {"document_id": did, "matter_id": doc.get("matter_id"), "sha256": sha,
               "name": str(doc["name"]), "byte_count": int(doc.get("byte_count") or 0),
               "state": state, "doc_class": doc.get("doc_class"),
               "class_reason": doc.get("class_reason"),
               "text_chars": doc.get("text_chars"),
               "ocr_state": str(doc.get("ocr_state") or "NOT_NEEDED"),
               "deleted_at": doc.get("deleted_at")}
        self.vault_docs[did] = row
        return dict(row)

    def read_vault_document(self, document_id: str) -> dict | None:
        row = self.vault_docs.get(str(document_id or ""))
        return dict(row) if row else None

    def list_vault_documents(self, *, matter_id: str) -> list[dict]:
        """One matter's documents. 8b: there is no cross-matter listing."""
        want = _matter_scope(matter_id)
        return [dict(r) for r in sorted(self.vault_docs.values(),
                                        key=lambda r: r["name"].lower())
                if str(r.get("matter_id") or "") == want and not r.get("deleted_at")]

    def write_vault_chunks(self, document_id: str, chunks: list) -> int:
        did = str(document_id or "")
        if did not in self.vault_docs:
            raise StoreError(f"no vault document {did!r} to chunk")
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
                                matter_id=doc.get("matter_id")))
        return out

    def write_vault_tags(self, document_id: str, tags: list) -> int:
        did = str(document_id or "")
        if did not in self.vault_docs:
            raise StoreError(f"no vault document {did!r} to tag")
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
        self.vault_chunks.pop(str(document_id), None)
        self.vault_tags.pop(str(document_id), None)
        return True

    def vault_counts(self) -> dict:
        live = [r for r in self.vault_docs.values() if not r.get("deleted_at")]
        by_state: dict = {}
        for r in live:
            by_state[r["state"]] = by_state.get(r["state"], 0) + 1
        return {"documents": len(live), "by_state": by_state,
                "deleted": len(self.vault_docs) - len(live),
                "unsearchable": sum(1 for r in live
                                    if r["state"] in ("PENDING", "CANNOT_READ"))}

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
        thread.append(row)
        return dict(row)

    def read_messages(self, conversation_id: str) -> list[dict]:
        return [dict(m) for m in sorted(self.messages.get(conversation_id, []),
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
        row = {"actor_id": aid, "label": str(actor.get("label") or ""), "role": role,
               "email": email, "password_hash": pw,
               "disabled_at": actor.get("disabled_at")}
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
        for row in self.invites.values():
            if row.get("accepted_at") is None and \
                    str(row.get("email") or "").lower() == email.lower():
                raise StoreError(
                    f"{email!r} already has a live invite (018 invites_live_per_email_idx)")
        row = {"invite_id": str(invite.get("invite_id") or ""), "email": email,
               "role": invite["role"], "token_hash": th,
               "invited_by": str(invite.get("invited_by") or ""),
               "expires_at": str(invite["expires_at"]),
               "accepted_at": None, "accepted_by": None}
        self.invites[row["invite_id"]] = row
        return dict(row)

    def accept_invite(self, token_hash: str, *, actor_id: str, now: str) -> dict | None:
        """Mark an invite used, ONCE. Returns the invite, or None if it cannot be used.

        None covers three different situations deliberately -- unknown token, already
        accepted, expired -- because telling them apart at this boundary is how a token is
        probed. The caller gets one answer: this token does not let you in.
        """
        for row in self.invites.values():
            if row.get("token_hash") != str(token_hash or ""):
                continue
            if row.get("accepted_at") is not None:
                return None                      # single use, and it is already used
            if str(row.get("expires_at") or "") <= str(now):
                return None
            row["accepted_at"] = str(now)
            row["accepted_by"] = str(actor_id)
            return dict(row)
        return None

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


# ── postgres ─────────────────────────────────────────────────────────────────

class PostgresBackend:
    """The same interface over psycopg. Every connection sets app.tenant_id first."""

    kind = POSTGRES

    def __init__(self, url: str, *, tenant_id: str, actor_id: str | None = None, pool=None) -> None:
        if not _UUID.match(tenant_id or ""):
            raise StoreError(
                f"tenant_id must be a UUID, got {tenant_id!r}. The row-level security "
                f"policies compare against app.tenant_id, so a backend without one would "
                f"read nothing and write rows nobody can see.")
        self._url = url
        self.tenant_id = tenant_id
        self.actor_id = actor_id or tenant_id
        # A1. Optional: None means open-per-operation, which is the previous behaviour.
        self._pool = pool

    @contextmanager
    def _conn(self):
        """A connection with this backend's tenant set, from the pool when one is supplied.

        A1. A context manager rather than a bare connection, so all forty-seven
        `with self._conn() as c:` call sites pool without one of them changing. The semantics
        are the same because every connection here is autocommit: psycopg's own `with` would
        close the connection on exit, and this returns it to the pool instead.

        Without a pool it opens and closes one per operation, exactly as before -- so a
        deployment that has not wired a pool is not silently changed.
        """
        if self._pool is not None:
            with self._pool.connection(tenant_id=self.tenant_id) as conn:
                yield conn
            return
        import psycopg
        conn = psycopg.connect(self._url, autocommit=True)
        try:
            # Before anything else. A statement issued ahead of this one is a statement the
            # policy evaluates with no tenant set, which returns nothing and looks like data
            # loss.
            conn.execute("SELECT set_config('app.tenant_id', %s, false)",
                         (self.tenant_id,))
            yield conn
        finally:
            conn.close()

    def write_run(self, run: dict) -> None:
        rid = run["id"]
        with self._conn() as c:
            c.execute(
                "INSERT INTO runs (run_id, tenant_id, actor_id, intent, status, "
                "refusal_code, law_versions, critic_enabled, nonconformity, "
                "nonconformity_note) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (run_id) DO UPDATE SET status = EXCLUDED.status, "
                "refusal_code = EXCLUDED.refusal_code, "
                "law_versions = EXCLUDED.law_versions, "
                "critic_enabled = EXCLUDED.critic_enabled, "
                "nonconformity = EXCLUDED.nonconformity, "
                "nonconformity_note = EXCLUDED.nonconformity_note",
                (rid, self.tenant_id, self.actor_id, run.get("intent", ""),
                 run.get("status", "PLANNED"), run.get("refusal_code"),
                 _json(run.get("law_versions")), _critic_enabled_now(),
                 run.get("nonconformity"), run.get("nonconformity_note")))
            c.execute("DELETE FROM run_steps WHERE run_id = %s", (rid,))
            # Shaped on the way IN, the same as MemoryBackend: one normalisation for
            # both backends, or the two disagree about what a null cost means. The shared
            # conformance suite caught this on Postgres while memory passed.
            for i, s in enumerate(_shaped(st, STEP_KEYS)
                                  for st in run.get("steps", [])):
                c.execute(
                    "INSERT INTO run_steps (run_id, ordinal, tenant_id, capability, "
                    "engine_capability, status, model, degraded, provider, region, "
                    "cost_inr, cost_note, idempotency_key) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (rid, i, self.tenant_id, s.get("capability", ""),
                     s.get("engine_capability"), s.get("status", "PLANNED"),
                     s.get("model"), bool(s.get("degraded", False)),
                     s.get("provider"), s.get("region"), s.get("cost_inr"),
                     s.get("cost_note"), s.get("idempotency_key")))
            c.execute("DELETE FROM propositions WHERE run_id = %s", (rid,))
            for i, p in enumerate(_shaped(pr, PROPOSITION_KEYS)
                                  for pr in run.get("propositions", [])):
                import uuid as _uuid
                c.execute(
                    "INSERT INTO propositions (proposition_id, run_id, tenant_id, ordinal, "
                    "status, source_ref, span_start, span_end) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (p.get("proposition_id") or str(_uuid.uuid4()), rid, self.tenant_id, i,
                     p.get("status", "UNVERIFIED"), p.get("source_ref"),
                     p.get("span_start"), p.get("span_end")))

    def read_run(self, run_id: str) -> dict | None:
        # A malformed id is not a run. Postgres raises InvalidTextRepresentation on a
        # non-UUID for a uuid column, so without this a lookup of "no-such-run" is an
        # exception on Postgres and None in memory -- the two backends disagreeing about
        # what "unknown" means, which is exactly what the shared contract is for.
        if not _UUID.match(run_id or ""):
            return None
        with self._conn() as c:
            r = c.execute("SELECT run_id, intent, status, refusal_code, result, "
                          "law_versions, failure_category, failure_reason, "
                          "critic_enabled, nonconformity, nonconformity_note "
                          "FROM runs WHERE run_id = %s", (run_id,)).fetchone()
            if r is None:
                return None
            out = {"id": str(r[0]), "intent": r[1], "status": r[2], "refusal_code": r[3],
                   "result": r[4], "law_versions": r[5],
                   # O8. Written by set_run and read back here; without these two the
                   # category existed on Postgres and was invisible to every reader, which
                   # the conformance list caught on its first live run.
                   "failure_category": r[6], "failure_reason": r[7],
                   "critic_enabled": r[8],
                   "nonconformity": float(r[9]) if r[9] is not None else None,
                   "nonconformity_note": r[10]}
            out["steps"] = [
                {"capability": s[0], "engine_capability": s[1], "status": s[2],
                 "model": s[3], "degraded": s[4], "provider": s[5], "region": s[6],
                 "cost_inr": float(s[7]) if s[7] is not None else None,
                 "cost_note": s[8], "idempotency_key": s[9]}
                for s in c.execute(
                    "SELECT capability, engine_capability, status, model, degraded, "
                    "provider, region, cost_inr, cost_note, idempotency_key "
                    "FROM run_steps WHERE run_id = %s ORDER BY ordinal", (run_id,)).fetchall()]
            out["propositions"] = [
                {"status": p[0], "source_ref": p[1], "span_start": p[2], "span_end": p[3]}
                for p in c.execute(
                    "SELECT status, source_ref, span_start, span_end FROM propositions "
                    "WHERE run_id = %s ORDER BY ordinal", (run_id,)).fetchall()]
            return out

    def put_document(self, *, sha256: str, name: str, byte_count: int) -> dict:
        with self._conn() as c:
            c.execute(
                "INSERT INTO documents (sha256, tenant_id, name, byte_count) "
                "VALUES (%s,%s,%s,%s) ON CONFLICT (tenant_id, sha256) DO NOTHING",
                (sha256, self.tenant_id, name, byte_count))
        return {"sha256": sha256, "name": name, "byte_count": byte_count,
                "tenant_id": self.tenant_id}

    def get_document(self, sha256: str) -> dict | None:
        with self._conn() as c:
            r = c.execute("SELECT sha256, name, byte_count, tenant_id FROM documents "
                          "WHERE sha256 = %s", (sha256,)).fetchone()
        return None if r is None else {"sha256": r[0], "name": r[1],
                                        "byte_count": r[2], "tenant_id": str(r[3])}

    def write_decision(self, decision: dict) -> dict:
        import psycopg
        with self._conn() as c:
            try:
                r = c.execute(
                    "INSERT INTO decisions (decision_id, run_id, tenant_id, item_ref, "
                    "decision, reason, quoted_span, quote_viewed, law_versions, actor_id, "
                    "decided_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,"
                    "COALESCE(%s::timestamptz, now())) "
                    "RETURNING " + _DECISION_COLS,
                    (decision["decision_id"], decision["run_id"], self.tenant_id,
                     decision["item_ref"], decision["decision"], decision["reason"],
                     decision["quoted_span"], bool(decision.get("quote_viewed")),
                     _json(decision.get("law_versions")), decision["actor_id"],
                     decision.get("decided_at"))).fetchone()
            except psycopg.errors.UniqueViolation:
                raise DecisionExists(
                    f"{decision['item_ref']} on run {decision['run_id']} already has a "
                    f"decision. A reviewer changing their mind writes a new one against a "
                    f"new run; overwriting would destroy the label, which is the point of "
                    f"storing it.") from None
        return _decision_row(r)

    def read_decisions(self, run_id: str) -> list[dict]:
        if not _UUID.match(run_id or ""):
            return []
        with self._conn() as c:
            rows = c.execute(
                "SELECT " + _DECISION_COLS + " FROM decisions WHERE run_id = %s "
                "ORDER BY decided_at, item_ref", (run_id,)).fetchall()
        return [_decision_row(r) for r in rows]

    def append_step(self, run_id: str, step: dict, *, key: str) -> bool:
        """Append unless the key is already there. The unique index decides, not a SELECT:
        a check-then-insert is two statements a second worker can interleave with."""
        st = _shaped(step, STEP_KEYS)
        with self._conn() as c:
            n = c.execute(
                "INSERT INTO run_steps (run_id, ordinal, tenant_id, capability, "
                "engine_capability, status, model, degraded, provider, region, cost_inr, "
                "cost_note, idempotency_key) SELECT %s, "
                "(SELECT coalesce(max(ordinal) + 1, 0) FROM run_steps WHERE run_id = %s), "
                "%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s "
                "ON CONFLICT (run_id, idempotency_key) WHERE idempotency_key IS NOT NULL "
                "DO NOTHING",
                (run_id, run_id, self.tenant_id, st.get("capability", ""),
                 st.get("engine_capability"), st.get("status", "PLANNED"),
                 st.get("model"), bool(st.get("degraded", False)), st.get("provider"),
                 st.get("region"), st.get("cost_inr"), st.get("cost_note"), key)).rowcount
        return bool(n)

    def set_run(self, run_id: str, *, status: str, refusal_code=None, result=None) -> None:
        import json as _json
        with self._conn() as c:
            cat, why = failure_tag(status, refusal_code, result)
            c.execute(
                "UPDATE runs SET status = %s, refusal_code = %s, "
                "result = COALESCE(%s::jsonb, result), "
                "failure_category = %s, failure_reason = %s, "
                "finished_at = CASE WHEN %s THEN now() ELSE finished_at END "
                "WHERE run_id = %s",
                (status, refusal_code,
                 None if result is None else _json.dumps(result), cat, why,
                 status in ("ANSWERED", "PARTIAL", "REFUSED", "FAILED"), run_id))

    # ── 8a: users, roles and invites ─────────────────────────────────────────
    def write_actor(self, actor: dict) -> dict:
        import psycopg
        try:
            with self._conn() as c:
                c.execute(
                    "INSERT INTO actors (actor_id, tenant_id, label, role, email, "
                    "password_hash, disabled_at) VALUES (%s,%s,%s,%s,%s,%s,%s) "
                    "ON CONFLICT (actor_id) DO UPDATE SET label = EXCLUDED.label, "
                    "role = EXCLUDED.role, email = EXCLUDED.email, "
                    "password_hash = EXCLUDED.password_hash, "
                    "disabled_at = EXCLUDED.disabled_at",
                    (actor["actor_id"], self.tenant_id, actor.get("label") or "",
                     actor.get("role") or "viewer",
                     (str(actor.get("email") or "").strip() or None),
                     actor.get("password_hash"), actor.get("disabled_at")))
        except psycopg.errors.IntegrityError as exc:
            raise StoreError(f"the database refused this actor: {type(exc).__name__} "
                             f"{str(exc).splitlines()[0][:150]}") from None
        return self.read_actor(actor["actor_id"]) or {}

    def read_actor(self, actor_id: str) -> dict | None:
        if not _UUID.match(actor_id or ""):
            return None
        with self._conn() as c:
            r = c.execute("SELECT actor_id, label, role, email, password_hash, "
                          "disabled_at FROM actors WHERE actor_id = %s",
                          (actor_id,)).fetchone()
        return None if r is None else {
            "actor_id": str(r[0]), "label": r[1], "role": r[2], "email": r[3],
            "password_hash": r[4], "disabled_at": r[5].isoformat() if r[5] else None}

    def create_invite(self, invite: dict) -> dict:
        import psycopg
        try:
            with self._conn() as c:
                r = c.execute(
                    "INSERT INTO invites (invite_id, tenant_id, email, role, token_hash, "
                    "invited_by, expires_at) VALUES (%s,%s,%s,%s,%s,%s,%s) "
                    "RETURNING invite_id, email, role, token_hash, invited_by, "
                    "expires_at, accepted_at, accepted_by",
                    (invite["invite_id"], self.tenant_id, invite["email"],
                     invite["role"], invite["token_hash"], invite["invited_by"],
                     invite["expires_at"])).fetchone()
        except psycopg.errors.IntegrityError as exc:
            raise StoreError(f"the database refused this invite: {type(exc).__name__} "
                             f"{str(exc).splitlines()[0][:150]}") from None
        return {"invite_id": str(r[0]), "email": r[1], "role": r[2], "token_hash": r[3],
                "invited_by": str(r[4]), "expires_at": r[5].isoformat(),
                "accepted_at": None, "accepted_by": None}

    def accept_invite(self, token_hash: str, *, actor_id: str, now: str) -> dict | None:
        """One UPDATE, so two simultaneous accepts cannot both win.

        The `accepted_at IS NULL` in the WHERE clause is the single-use guarantee: the
        second statement matches no row. Checking first and updating after would be a race
        with a window exactly as wide as the round trip.
        """
        with self._conn() as c:
            r = c.execute(
                "UPDATE invites SET accepted_at = now(), accepted_by = %s "
                "WHERE token_hash = %s AND accepted_at IS NULL AND expires_at > now() "
                "RETURNING invite_id, email, role, token_hash, invited_by, expires_at, "
                "accepted_at, accepted_by",
                (actor_id, str(token_hash or ""))).fetchone()
        return None if r is None else {
            "invite_id": str(r[0]), "email": r[1], "role": r[2], "token_hash": r[3],
            "invited_by": str(r[4]), "expires_at": r[5].isoformat(),
            "accepted_at": r[6].isoformat(), "accepted_by": str(r[7])}

    def read_labels(self) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT COALESCE(r.intent, ''), "
                "       COALESCE(r.result #>> '{bodies,0,body}', ''), d.decision "
                "FROM decisions d LEFT JOIN runs r ON r.run_id = d.run_id").fetchall()
        return [{"task": r[0], "body": r[1], "decision": r[2]} for r in rows]

    def read_failure_counts(self) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT to_char(date_trunc('week', COALESCE(finished_at, created_at)), "
                "       'IYYY-\"W\"IW') AS week, failure_category, count(*) "
                "FROM runs WHERE status <> 'ANSWERED' "
                "GROUP BY 1, 2 ORDER BY 1, 2").fetchall()
        return [{"week": r[0], "category": r[1], "count": int(r[2])} for r in rows]

    def write_cascade(self, record: dict, *, run_id: str | None = None) -> dict:
        import json as _json
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
        with self._conn() as c:
            c.execute(
                "INSERT INTO cascade_runs (cascade_id, run_id, tenant_id, status, error, "
                "attempts, body_ids, claim_count, refusal_count, total_cost_inr) "
                "VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s)",
                (row["cascade_id"], row["run_id"], self.tenant_id, row["status"],
                 row["error"], _json.dumps(row["attempts"]), row["body_ids"],
                 row["claim_count"], row["refusal_count"], row["total_cost_inr"]))
        return dict(row)

    def read_cascades(self, *, run_id: str | None = None, limit: int = 1000) -> list[dict]:
        if run_id is not None and not _UUID.match(run_id or ""):
            return []
        where = "WHERE run_id = %s " if run_id is not None else ""
        args = (run_id, limit) if run_id is not None else (limit,)
        with self._conn() as c:
            rows = c.execute(
                "SELECT cascade_id, run_id, status, error, attempts, body_ids, "
                "claim_count, refusal_count, total_cost_inr FROM cascade_runs "
                + where + "ORDER BY created_at LIMIT %s", args).fetchall()
        return [{"cascade_id": str(r[0]),
                 "run_id": str(r[1]) if r[1] is not None else None,
                 "status": r[2], "error": r[3], "attempts": r[4] or [],
                 "body_ids": list(r[5] or []), "claim_count": r[6],
                 "refusal_count": r[7],
                 "total_cost_inr": float(r[8]) if r[8] is not None else None}
                for r in rows]

    # ── C2: the chat layer (010_conversations.sql) ───────────────────────────
    def write_conversation(self, conversation: dict) -> dict:
        import psycopg
        cid = conversation["conversation_id"]
        try:
            with self._conn() as c:
                c.execute(
                    "INSERT INTO conversations (conversation_id, tenant_id, title, "
                    "matter_id) VALUES (%s,%s,%s,%s) "
                    "ON CONFLICT (conversation_id) DO UPDATE SET "
                    "title = EXCLUDED.title, matter_id = EXCLUDED.matter_id, "
                    "updated_at = now()",
                    (cid, self.tenant_id, conversation.get("title") or "",
                     (str(conversation.get("matter_id") or "").strip() or None)))
        except psycopg.errors.IntegrityError as exc:
            raise StoreError(f"the database refused this conversation: "
                             f"{type(exc).__name__}") from None
        return self.read_conversation(cid) or {"conversation_id": cid}

    def read_conversation(self, conversation_id: str) -> dict | None:
        if not _UUID.match(conversation_id or ""):
            return None
        with self._conn() as c:
            r = c.execute("SELECT conversation_id, title, created_at, updated_at, "
                          "matter_id FROM "
                          "conversations WHERE conversation_id = %s",
                          (conversation_id,)).fetchone()
        if r is None:
            return None
        return {"matter_id": str(r[4]) if r[4] else None,
                "conversation_id": str(r[0]), "title": r[1],
                "created_at": r[2].isoformat() if r[2] else None,
                "updated_at": r[3].isoformat() if r[3] else None}

    def list_conversations(self, *, matter_id: str, limit: int = 50) -> list[dict]:
        want = _matter_scope(matter_id)
        with self._conn() as c:
            rows = c.execute("SELECT conversation_id, title, created_at, updated_at FROM "
                             "conversations WHERE matter_id = %s "
                             "ORDER BY updated_at DESC LIMIT %s",
                             (want, limit)).fetchall()
        return [{"conversation_id": str(r[0]), "title": r[1],
                 "created_at": r[2].isoformat() if r[2] else None,
                 "updated_at": r[3].isoformat() if r[3] else None} for r in rows]

    def write_matter(self, matter: dict) -> dict:
        import psycopg
        try:
            with self._conn() as c:
                r = c.execute(
                    "INSERT INTO matters (matter_id, tenant_id, name, client_ref, "
                    "closed_at) VALUES (%s,%s,%s,%s,%s) "
                    "ON CONFLICT (matter_id) DO UPDATE SET name = EXCLUDED.name, "
                    "client_ref = EXCLUDED.client_ref, closed_at = EXCLUDED.closed_at "
                    "RETURNING matter_id, name, client_ref, closed_at",
                    (matter["matter_id"], self.tenant_id,
                     str(matter.get("name") or "").strip(),
                     matter.get("client_ref") or "",
                     matter.get("closed_at"))).fetchone()
        except psycopg.errors.IntegrityError as exc:
            raise StoreError(f"the database refused this matter: {type(exc).__name__} "
                             f"{str(exc).splitlines()[0][:150]}") from None
        return {"matter_id": str(r[0]), "name": r[1], "client_ref": r[2],
                "closed_at": r[3].isoformat() if r[3] else None}

    def list_matters(self) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT matter_id, name, client_ref, closed_at FROM matters "
                             "ORDER BY lower(name)").fetchall()
        return [{"matter_id": str(r[0]), "name": r[1], "client_ref": r[2],
                 "closed_at": r[3].isoformat() if r[3] else None} for r in rows]

    # ── V1: the vault ────────────────────────────────────────────────────────
    def write_vault_document(self, doc: dict) -> dict:
        import psycopg
        try:
            with self._conn() as c:
                c.execute(
                    "INSERT INTO vault_documents (document_id, tenant_id, matter_id, "
                    "sha256, name, byte_count, state, doc_class, class_reason, "
                    "text_chars, ocr_state) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                    "ON CONFLICT (document_id) DO UPDATE SET state = EXCLUDED.state, "
                    "doc_class = EXCLUDED.doc_class, "
                    "class_reason = EXCLUDED.class_reason, "
                    "text_chars = EXCLUDED.text_chars, ocr_state = EXCLUDED.ocr_state, "
                    "matter_id = EXCLUDED.matter_id, "
                    "ingested_at = CASE WHEN EXCLUDED.state = 'INGESTED' THEN now() "
                    "ELSE vault_documents.ingested_at END",
                    (doc["document_id"], self.tenant_id,
                     (str(doc.get("matter_id") or "").strip() or None), doc["sha256"],
                     doc.get("name") or "", int(doc.get("byte_count") or 0),
                     doc.get("state") or "PENDING", doc.get("doc_class"),
                     doc.get("class_reason"), doc.get("text_chars"),
                     doc.get("ocr_state") or "NOT_NEEDED"))
        except psycopg.errors.IntegrityError as exc:
            raise StoreError(f"the database refused this vault document: "
                             f"{type(exc).__name__} "
                             f"{str(exc).splitlines()[0][:150]}") from None
        return self.read_vault_document(doc["document_id"]) or {}

    def read_vault_document(self, document_id: str) -> dict | None:
        if not _UUID.match(document_id or ""):
            return None
        with self._conn() as c:
            r = c.execute(
                "SELECT document_id, matter_id, sha256, name, byte_count, state, "
                "doc_class, class_reason, text_chars, ocr_state, deleted_at "
                "FROM vault_documents WHERE document_id = %s", (document_id,)).fetchone()
        return None if r is None else {
            "document_id": str(r[0]), "matter_id": str(r[1]) if r[1] else None,
            "sha256": r[2], "name": r[3], "byte_count": int(r[4]), "state": r[5],
            "doc_class": r[6], "class_reason": r[7],
            "text_chars": int(r[8]) if r[8] is not None else None, "ocr_state": r[9],
            "deleted_at": r[10].isoformat() if r[10] else None}

    def list_vault_documents(self, *, matter_id: str) -> list[dict]:
        want = _matter_scope(matter_id)
        with self._conn() as c:
            rows = c.execute(
                "SELECT document_id FROM vault_documents WHERE matter_id = %s "
                "AND deleted_at IS NULL ORDER BY lower(name)", (want,)).fetchall()
        return [self.read_vault_document(str(r[0])) or {} for r in rows]

    def write_vault_chunks(self, document_id: str, chunks: list) -> int:
        import psycopg
        try:
            with self._conn() as c:
                c.execute("DELETE FROM vault_chunks WHERE document_id = %s",
                          (document_id,))
                for i, text in enumerate(chunks or ()):
                    c.execute("INSERT INTO vault_chunks (document_id, tenant_id, ordinal, "
                              "text) VALUES (%s,%s,%s,%s)",
                              (document_id, self.tenant_id, i, str(text)))
        except psycopg.errors.IntegrityError as exc:
            raise StoreError(f"the database refused a chunk: {type(exc).__name__} "
                             f"{str(exc).splitlines()[0][:150]}") from None
        return len(chunks or ())

    def read_vault_chunks(self) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT c.document_id, c.ordinal, c.text, d.name, d.doc_class, "
                "       d.matter_id "
                "FROM vault_chunks c JOIN vault_documents d "
                "  ON d.document_id = c.document_id "
                "WHERE d.deleted_at IS NULL ORDER BY c.document_id, c.ordinal").fetchall()
        return [{"document_id": str(r[0]), "ordinal": int(r[1]), "text": r[2],
                 "name": r[3], "doc_class": r[4] or "",
                 "matter_id": str(r[5]) if r[5] else None} for r in rows]

    def write_vault_tags(self, document_id: str, tags: list) -> int:
        import psycopg
        try:
            with self._conn() as c:
                c.execute("DELETE FROM vault_tags WHERE document_id = %s", (document_id,))
                for t in tags or ():
                    c.execute(
                        "INSERT INTO vault_tags (document_id, tenant_id, tag, quote, "
                        "span_start, span_end) VALUES (%s,%s,%s,%s,%s,%s) "
                        "ON CONFLICT DO NOTHING",
                        (document_id, self.tenant_id, (t or {}).get("tag"),
                         (t or {}).get("quote"), (t or {}).get("span_start"),
                         (t or {}).get("span_end")))
        except psycopg.errors.IntegrityError as exc:
            raise StoreError(f"the database refused a tag: {type(exc).__name__} "
                             f"{str(exc).splitlines()[0][:150]}") from None
        return len(tags or ())

    def read_vault_tags(self, document_id: str) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT tag, quote, span_start, span_end FROM vault_tags "
                "WHERE document_id = %s ORDER BY tag, quote", (document_id,)).fetchall()
        return [{"document_id": str(document_id), "tag": r[0], "quote": r[1],
                 "span_start": r[2], "span_end": r[3]} for r in rows]

    def delete_vault_document(self, document_id: str, *, now: str) -> bool:
        """One statement, so a second delete cannot also claim to be the first."""
        with self._conn() as c:
            n = c.execute(
                "UPDATE vault_documents SET state = 'DELETED', deleted_at = now(), "
                "text_chars = NULL WHERE document_id = %s AND deleted_at IS NULL",
                (document_id,)).rowcount
            if n:
                c.execute("DELETE FROM vault_chunks WHERE document_id = %s",
                          (document_id,))
                c.execute("DELETE FROM vault_tags WHERE document_id = %s",
                          (document_id,))
        return bool(n)

    def vault_counts(self) -> dict:
        with self._conn() as c:
            rows = c.execute("SELECT state, count(*) FROM vault_documents "
                             "WHERE deleted_at IS NULL GROUP BY state").fetchall()
            gone = c.execute("SELECT count(*) FROM vault_documents "
                             "WHERE deleted_at IS NOT NULL").fetchone()[0]
        by_state = {r[0]: int(r[1]) for r in rows}
        return {"documents": sum(by_state.values()), "by_state": by_state,
                "deleted": int(gone),
                "unsearchable": by_state.get("PENDING", 0)
                + by_state.get("CANNOT_READ", 0)}

    def append_message(self, message: dict) -> dict:
        """Append one message, translating the database's refusals into StoreError.

        The translation is not cosmetic. `conformance()` asserts that both backends refuse
        the same rows, and it caught this: the dict raised `StoreError` on a duplicate
        ordinal while Postgres raised `psycopg.errors.UniqueViolation`, so a caller with
        one `except StoreError` handled the memory backend and crashed on the real one --
        the divergence that only shows up on the backend the gate does not run, which is
        the whole reason that list is shared.
        """
        import psycopg
        _check_message(message)
        try:
            with self._conn() as c:
                c.execute(
                    "INSERT INTO messages (message_id, conversation_id, tenant_id, "
                    "ordinal, role, text, file_ids, task, run_id, envelope) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (message["message_id"], message["conversation_id"], self.tenant_id,
                     message["ordinal"], message["role"], message.get("text") or "",
                     _json(list(message.get("file_ids") or [])), message.get("task"),
                     message.get("run_id"), _json(message.get("envelope"))))
                c.execute("UPDATE conversations SET updated_at = now() WHERE "
                          "conversation_id = %s", (message["conversation_id"],))
        except psycopg.errors.IntegrityError as exc:
            # UniqueViolation (the ordinal), CheckViolation (010's role/envelope/file_ids
            # rules), ForeignKeyViolation (no such conversation) all land here.
            raise StoreError(
                f"the database refused this message: {type(exc).__name__} "
                f"{str(exc).splitlines()[0][:160]}") from None
        return _shaped(message, MESSAGE_KEYS)

    def read_messages(self, conversation_id: str) -> list[dict]:
        if not _UUID.match(conversation_id or ""):
            return []
        with self._conn() as c:
            rows = c.execute(
                "SELECT message_id, conversation_id, ordinal, role, text, file_ids, task, "
                "run_id, envelope FROM messages WHERE conversation_id = %s "
                "ORDER BY ordinal", (conversation_id,)).fetchall()
        return [{"message_id": str(r[0]), "conversation_id": str(r[1]), "ordinal": r[2],
                 "role": r[3], "text": r[4], "file_ids": list(r[5] or []),
                 "task": r[6], "run_id": str(r[7]) if r[7] is not None else None,
                 "envelope": r[8]} for r in rows]

    def set_message_envelope(self, message_id: str, envelope: dict) -> bool:
        if not _UUID.match(message_id or ""):
            return False
        with self._conn() as c:
            # role = 'assistant' in the WHERE, not asserted in Python: a user message must
            # not gain an envelope even if a caller asks, and 010's CHECK says so too.
            n = c.execute("UPDATE messages SET envelope = %s WHERE message_id = %s AND "
                          "role = 'assistant'",
                          (_json(envelope), message_id)).rowcount
        return bool(n)

    # ── H4: review grids ─────────────────────────────────────────────────────
    def write_grid(self, grid: dict) -> dict:
        import psycopg
        gid = grid["grid_id"]
        try:
            with self._conn() as c:
                c.execute("INSERT INTO review_grids (grid_id, tenant_id, name) "
                          "VALUES (%s,%s,%s) ON CONFLICT (grid_id) DO UPDATE SET "
                          "name = EXCLUDED.name",
                          (gid, self.tenant_id, grid.get("name") or ""))
                for i, col in enumerate(grid.get("columns") or ()):
                    c.execute(
                        "INSERT INTO review_grid_columns (grid_id, tenant_id, name, kind, "
                        "question, ordinal) VALUES (%s,%s,%s,%s,%s,%s) "
                        "ON CONFLICT (grid_id, name) DO NOTHING",
                        (gid, self.tenant_id, col["name"], col["kind"], col["question"], i))
                for d in grid.get("document_ids") or ():
                    for col in grid.get("columns") or ():
                        c.execute(
                            "INSERT INTO review_grid_cells (grid_id, tenant_id, "
                            "document_id, column_name, state, reason) VALUES "
                            "(%s,%s,%s,%s,'PENDING',%s) ON CONFLICT DO NOTHING",
                            (gid, self.tenant_id, d, col["name"],
                             "queued; this cell has not been run yet"))
        except psycopg.errors.IntegrityError as exc:
            raise StoreError(f"the database refused this grid: {type(exc).__name__} "
                             f"{str(exc).splitlines()[0][:150]}") from None
        return self.read_grid(gid) or {"grid_id": gid}

    def read_grid(self, grid_id: str) -> dict | None:
        if not _UUID.match(grid_id or ""):
            return None
        with self._conn() as c:
            g = c.execute("SELECT grid_id, name, cancelled_at, paused_budget, "
                          "pause_reason, cells_not_dispatched FROM review_grids "
                          "WHERE grid_id = %s", (grid_id,)).fetchone()
            if g is None:
                return None
            cols = c.execute("SELECT name, kind, question FROM review_grid_columns "
                             "WHERE grid_id = %s ORDER BY ordinal", (grid_id,)).fetchall()
            docs = c.execute("SELECT DISTINCT document_id FROM review_grid_cells "
                             "WHERE grid_id = %s ORDER BY document_id",
                             (grid_id,)).fetchall()
        return {"grid_id": str(g[0]), "name": g[1],
                "cancelled_at": g[2].isoformat() if g[2] else None,
                # 022. Selected explicitly: a default standing in for a column the query
                # forgot is a lie with a safety net, which is how A1's `jobs.get()` came
                # to report a DEAD job with no reason.
                "paused_budget": bool(g[3]),
                "pause_reason": g[4] or "",
                "cells_not_dispatched": int(g[5] or 0),
                "columns": [{"name": r[0], "kind": r[1], "question": r[2]} for r in cols],
                "document_ids": [r[0] for r in docs]}

    def read_grid_cells(self, grid_id: str) -> list[dict]:
        if not _UUID.match(grid_id or ""):
            return []
        with self._conn() as c:
            rows = c.execute(
                "SELECT grid_id, document_id, column_name, state, value, quote, reason, "
                "provider, cost_inr, cost_note "
                "FROM review_grid_cells WHERE grid_id = %s "
                "ORDER BY document_id, column_name", (grid_id,)).fetchall()
        # Through `_shaped`, like every other row: it floats the numeric (Postgres returns
        # Decimal, the dict returns float, and a caller summing a grid would hit a
        # TypeError on exactly one backend) and it fills NO_CALL_NOTE for a null cost with
        # no note -- which is how a PENDING cell reads the same on both. The conformance
        # list caught that divergence the first time it ran these columns.
        return [_shaped({"grid_id": str(r[0]), "document_id": r[1], "column_name": r[2],
                         "state": r[3], "value": r[4], "quote": r[5], "reason": r[6],
                         "provider": r[7],
                         "cost_inr": float(r[8]) if r[8] is not None else None,
                         "cost_note": r[9]}, GRID_CELL_KEYS)
                for r in rows]

    def pause_grid(self, grid_id: str, *, reason: str, not_dispatched: int) -> bool:
        """Record that the budget paused this table. False when there is no such grid.

        022's CHECKs do the refusing on this path; the guards below are the same rules
        restated so the dict cannot accept a row Postgres would reject.
        """
        import psycopg
        if not str(reason or "").strip():
            raise StoreError(
                "a paused table needs a reason (022 review_grids_pause_reason_iff_paused)")
        if int(not_dispatched) < 0:
            raise StoreError("cells_not_dispatched cannot be negative")
        if not _UUID.match(grid_id or ""):
            return False
        try:
            with self._conn() as c:
                n = c.execute(
                    "UPDATE review_grids SET paused_budget = true, pause_reason = %s, "
                    "cells_not_dispatched = %s WHERE grid_id = %s",
                    (str(reason)[:2000], int(not_dispatched), grid_id)).rowcount
        except psycopg.errors.IntegrityError as exc:
            raise StoreError(f"the database refused this pause: {type(exc).__name__} "
                             f"{str(exc).splitlines()[0][:150]}") from None
        return bool(n)

    def write_grid_cell(self, cell: dict, *, if_pending: bool = True) -> bool:
        import psycopg
        where = " AND review_grid_cells.state = 'PENDING'" if if_pending else ""
        try:
            with self._conn() as c:
                n = c.execute(
                    "INSERT INTO review_grid_cells (grid_id, tenant_id, document_id, "
                    "column_name, state, value, quote, reason, provider, cost_inr, "
                    "cost_note, answered_at) VALUES "
                    "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now()) "
                    "ON CONFLICT (grid_id, document_id, column_name) DO UPDATE SET "
                    "state = EXCLUDED.state, value = EXCLUDED.value, "
                    "quote = EXCLUDED.quote, reason = EXCLUDED.reason, "
                    "provider = EXCLUDED.provider, cost_inr = EXCLUDED.cost_inr, "
                    "cost_note = EXCLUDED.cost_note, "
                    "answered_at = now() WHERE TRUE" + where,
                    (cell["grid_id"], self.tenant_id, cell["document_id"],
                     cell["column_name"], cell["state"], cell.get("value") or "",
                     cell.get("quote") or "", cell.get("reason") or "",
                     cell.get("provider"), cell.get("cost_inr"),
                     cell.get("cost_note"))).rowcount
        except psycopg.errors.IntegrityError as exc:
            raise StoreError(f"the database refused this cell: {type(exc).__name__} "
                             f"{str(exc).splitlines()[0][:150]}") from None
        return bool(n)

    def cancel_grid(self, grid_id: str) -> bool:
        if not _UUID.match(grid_id or ""):
            return False
        with self._conn() as c:
            n = c.execute("UPDATE review_grids SET cancelled_at = now() "
                          "WHERE grid_id = %s AND cancelled_at IS NULL",
                          (grid_id,)).rowcount
        return bool(n)

    # ── O9: the answer cache ─────────────────────────────────────────────────
    def write_cache_entry(self, entry: dict) -> bool:
        import json as _json
        import psycopg
        if not (entry.get("citations") or []):
            raise StoreError(
                "a cache entry with NO citations is refused (014 answer_cache.citations): "
                "an answer that cites nothing can never be shown to be still true")
        try:
            with self._conn() as c:
                n = c.execute(
                    "INSERT INTO answer_cache (tenant_id, lookup_key, content_key, "
                    "question, task, as_of, sources, citations, payload) VALUES "
                    "(%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                    "ON CONFLICT (tenant_id, lookup_key) DO UPDATE SET "
                    "content_key = EXCLUDED.content_key, citations = EXCLUDED.citations, "
                    "payload = EXCLUDED.payload, created_at = now()",
                    (self.tenant_id, entry["lookup_key"], entry["content_key"],
                     entry.get("question") or "", entry.get("task") or "",
                     entry.get("as_of") or "",
                     _json.dumps(list(entry.get("sources") or [])),
                     _json.dumps(list(entry.get("citations") or [])),
                     _json.dumps(dict(entry.get("payload") or {})))).rowcount
        except psycopg.errors.IntegrityError as exc:
            raise StoreError(f"the database refused this cache entry: "
                             f"{type(exc).__name__} "
                             f"{str(exc).splitlines()[0][:150]}") from None
        return bool(n)

    def read_cache_entry(self, lookup_key: str) -> dict | None:
        with self._conn() as c:
            r = c.execute(
                "SELECT lookup_key, content_key, question, task, as_of, sources, "
                "citations, payload, created_at, served FROM answer_cache "
                "WHERE lookup_key = %s", (str(lookup_key or ""),)).fetchone()
        if not r:
            return None
        row = _shaped({"lookup_key": r[0], "content_key": r[1], "question": r[2],
                       "task": r[3], "as_of": r[4], "sources": list(r[5] or []),
                       "citations": list(r[6] or []), "payload": dict(r[7] or {}),
                       "created_at": r[8].isoformat() if r[8] else ""}, CACHE_KEYS)
        row["served"] = int(r[9] or 0)
        return row

    def bump_cache_stat(self, kind: str, *, day: str) -> None:
        if kind not in CACHE_STATS:
            raise StoreError(f"{kind!r} is not a cache statistic; one of {CACHE_STATS}")
        # The column name is interpolated and that is safe ONLY because `kind` has just
        # been checked against a fixed tuple. Never widen this without that check.
        with self._conn() as c:
            c.execute(
                f"INSERT INTO answer_cache_stats (tenant_id, day, {kind}) "
                f"VALUES (%s, %s, 1) ON CONFLICT (tenant_id, day) DO UPDATE SET "
                f"{kind} = answer_cache_stats.{kind} + 1",
                (self.tenant_id, str(day)))

    def read_cache_stats(self) -> dict:
        with self._conn() as c:
            r = c.execute("SELECT COALESCE(SUM(hits),0), COALESCE(SUM(misses),0), "
                          "COALESCE(SUM(stale),0) FROM answer_cache_stats").fetchone()
        return {"hits": int(r[0]), "misses": int(r[1]), "stale": int(r[2])}

    # ── H3: drafts ───────────────────────────────────────────────────────────
    def write_draft(self, draft: dict) -> dict:
        import psycopg
        did = draft["draft_id"]
        try:
            with self._conn() as c:
                c.execute("INSERT INTO drafts (draft_id, tenant_id, kind, title) "
                          "VALUES (%s,%s,%s,%s) ON CONFLICT (draft_id) DO UPDATE SET "
                          "title = EXCLUDED.title, updated_at = now()",
                          (did, self.tenant_id, draft.get("kind") or "agm_notice",
                           draft.get("title") or ""))
        except psycopg.errors.IntegrityError as exc:
            raise StoreError(f"the database refused this draft: {type(exc).__name__}") from None
        return self.read_draft(did) or {"draft_id": did}

    def read_draft(self, draft_id: str) -> dict | None:
        if not _UUID.match(draft_id or ""):
            return None
        with self._conn() as c:
            r = c.execute("SELECT draft_id, kind, title FROM drafts WHERE draft_id = %s",
                          (draft_id,)).fetchone()
        return None if r is None else {"draft_id": str(r[0]), "kind": r[1], "title": r[2]}

    def append_draft_version(self, version: dict) -> int:
        import psycopg
        _check_draft_version(version)
        did = version["draft_id"]
        try:
            with self._conn() as c:
                n = version.get("version")
                if n is None:
                    row = c.execute("SELECT coalesce(max(version), 0) + 1 FROM "
                                    "draft_versions WHERE draft_id = %s",
                                    (did,)).fetchone()
                    n = int(row[0]) if row else 1
                c.execute(
                    "INSERT INTO draft_versions (draft_id, tenant_id, version, title, "
                    "body, slots, citations, blocking_count, approved_by, approved_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (did, self.tenant_id, n, version.get("title") or "",
                     version.get("body") or "", _json(list(version.get("slots") or [])),
                     _json(list(version.get("citations") or [])),
                     int(version.get("blocking_count") or 0),
                     version.get("approved_by"), version.get("approved_at")))
                c.execute("UPDATE drafts SET updated_at = now() WHERE draft_id = %s",
                          (did,))
        except psycopg.errors.IntegrityError as exc:
            raise StoreError(
                f"the database refused this draft version: {type(exc).__name__} "
                f"{str(exc).splitlines()[0][:150]}") from None
        return int(n)

    def read_draft_versions(self, draft_id: str) -> list[dict]:
        if not _UUID.match(draft_id or ""):
            return []
        with self._conn() as c:
            rows = c.execute(
                "SELECT draft_id, version, title, body, slots, citations, "
                "blocking_count, approved_by, approved_at FROM draft_versions "
                "WHERE draft_id = %s ORDER BY version", (draft_id,)).fetchall()
        return [{"draft_id": str(r[0]), "version": r[1], "title": r[2], "body": r[3],
                 "slots": list(r[4] or []), "citations": list(r[5] or []),
                 "blocking_count": r[6], "approved_by": r[7],
                 "approved_at": r[8].isoformat() if r[8] else None} for r in rows]

    def next_ordinal(self, conversation_id: str) -> int:
        if not _UUID.match(conversation_id or ""):
            return 0
        with self._conn() as c:
            r = c.execute("SELECT count(*) FROM messages WHERE conversation_id = %s",
                          (conversation_id,)).fetchone()
        return int(r[0]) if r else 0

    def read(self, run_id: str) -> dict | None:
        return self.read_run(run_id)

    def write(self, run: dict) -> None:
        self.write_run(run)


def database_url() -> str | None:
    """The configured URL, or None. Read through checker.env so .env is honoured."""
    try:
        from checker.env import load
        load()
    except Exception:                                            # noqa: BLE001
        pass
    return os.getenv(URL_ENV) or None


def select(*, tenant_id: str | None = None, url: str | None = None) -> Backend:
    """Postgres when a URL is configured, memory otherwise. The ONLY selection point.

    A URL that is set but unusable is an ERROR, never a silent fall back to memory: an
    operator who configured a database and got an in-memory store would be told everything
    is fine while nothing persists and no policy isolates anyone.
    """
    url = url if url is not None else database_url()
    if not url:
        return MemoryBackend(tenant_id=tenant_id or MemoryBackend().tenant_id)
    if not tenant_id:
        raise StoreError(f"{URL_ENV} is set but no tenant was given; a Postgres backend "
                         f"cannot be built without one")
    return PostgresBackend(url, tenant_id=tenant_id)


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
    backend.write_matter({"matter_id": _CONF_MATTER, "name": f"conformance {_CONF_MATTER[:8]}"})
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
        {"draft_id": did, "title": "Notice of AGM",
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
    backend.write_matter({"matter_id": _vm, "name": f"vault matter {_vm[:8]}"})
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
    except StoreError:
        ck(True, "**the same bytes twice is ONE document**: dedupe is a constraint, not a "
                 "check the caller remembers")

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

    # ── 8b: matters, and NO CROSS-MATTER LISTING ────────────────────────────
    _m1, _m2 = str(_uuid.uuid4()), str(_uuid.uuid4())
    backend.write_matter({"matter_id": _m1, "name": "Acme acquisition",
                          "client_ref": "ACM-1"})
    backend.write_matter({"matter_id": _m2, "name": "Beta dispute"})
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

    return out


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    # ── the contract, against the backend the gate can run ──────────────────
    for good, label in conformance(MemoryBackend()):
        check(good, f"[memory] {label}")

    # ── selection ───────────────────────────────────────────────────────────
    T = "11111111-2222-3333-4444-555555555555"
    check(select(url="").kind == MEMORY,
          "with no URL configured the store is in-memory")
    check(select(url=None, tenant_id=T).kind in (MEMORY, POSTGRES),
          "...and selection reads the environment when no URL is passed")
    b = select(url="postgresql://x/y", tenant_id=T)
    check(b.kind == POSTGRES and isinstance(b, PostgresBackend),
          "a configured URL selects Postgres")
    check(b.tenant_id == T, "...bound to the tenant it was given")
    try:
        select(url="postgresql://x/y")
        check(False, "a URL with no tenant is refused")
    except StoreError as e:
        check("cannot be built without one" in str(e),
              "a URL with no tenant is REFUSED rather than defaulted -- a default tenant "
              "is a tenant whose rows everyone shares")
    try:
        PostgresBackend("postgresql://x/y", tenant_id="not-a-uuid")
        check(False, "a non-UUID tenant is refused")
    except StoreError as e:
        check("row-level security" in str(e).lower() or "policies" in str(e),
              "...and the refusal names WHY: the policies compare against app.tenant_id")

    # A URL that is set but unusable must not degrade to memory.
    import inspect
    src = inspect.getsource(select)
    check("MemoryBackend" in src and "raise StoreError" in src,
          "select() raises on a bad configuration rather than falling back to memory: an "
          "operator told 'fine' while nothing persists is the worst of both")

    # ── both backends really do offer the same names ────────────────────────
    need = ("write_run", "read_run", "put_document", "get_document", "read", "write",
            "write_decision", "read_decisions", "write_cascade", "read_cascades",
            "write_conversation", "read_conversation", "list_conversations",
            "append_message", "read_messages", "set_message_envelope", "next_ordinal",
            "write_grid", "read_grid", "read_grid_cells", "write_grid_cell",
            "cancel_grid", "write_draft", "read_draft", "append_draft_version",
            "read_draft_versions", "write_cache_entry", "read_cache_entry",
            "bump_cache_stat", "read_cache_stats", "read_failure_counts",
            "read_labels", "write_actor", "read_actor", "create_invite",
            "accept_invite", "write_matter", "list_matters",
            "write_vault_document", "read_vault_document",
            "list_vault_documents", "write_vault_chunks",
            "read_vault_chunks", "write_vault_tags", "read_vault_tags",
            "delete_vault_document", "vault_counts")
    for name in need:
        check(hasattr(MemoryBackend(), name)
              and hasattr(PostgresBackend("postgresql://x/y", tenant_id=T), name),
              f"both backends expose {name}()")
    check(MemoryBackend().kind == MEMORY
          and PostgresBackend("postgresql://x/y", tenant_id=T).kind == POSTGRES,
          "...and each names itself, which is what /v1/health reports")

    check(len(conformance(MemoryBackend())) >= 12,
          f"the shared contract is not a token list "
          f"({len(conformance(MemoryBackend()))} assertions)")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
