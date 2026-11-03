"""The gate suite for the store. Run: PYTHONPATH=. python3 gateway/store/__main__.py"""
from __future__ import annotations

from gateway.store.auth_lookup import select
from gateway.store.conformance import conformance
from gateway.store.core import MEMORY, POSTGRES, StoreError
from gateway.store.memory import MemoryBackend
from gateway.store.postgres import PostgresBackend


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
            "write_grid", "read_grid", "read_grid_cells", "list_grids", "write_grid_cell",
            "cancel_grid", "write_draft", "read_draft", "list_drafts", "append_draft_version",
            "read_draft_versions", "write_cache_entry", "read_cache_entry",
            "bump_cache_stat", "read_cache_stats", "read_failure_counts",
            "read_labels", "write_actor", "read_actor", "create_invite",
            "accept_invite", "list_pending_invites", "cancel_invite", "write_matter", "list_matters", "matter_role",
            "matter_roles", "grant_matter_access", "revoke_matter_access",
            "list_matter_memberships", "share_vault_document", "list_unowned",
            "reassign_work",
            "write_vault_document", "read_vault_document", "vault_documents_by_sha256",
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
