"""External storage connector verbs — SharePoint/OneDrive first.

Verbs:
  connectors.authorize   → returns OAuth URL for user to visit
  connectors.callback    → exchanges code for tokens, stores them
  connectors.list_files  → list files in connected drive/folder
  connectors.import_file → download file, store in vault, optionally audit

Security:
  - Read-only scopes only.
  - Tokens encrypted at rest in the store.
  - Per-actor, per-matter token isolation.
  - File import creates a vault document — standard access controls apply.
"""
from __future__ import annotations

import hashlib
import sys
import time

from gateway.verbs.core import Context, _refuse


SUPPORTED_PROVIDERS = ("microsoft",)
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


def _connectors_authorize(args: dict, ctx: Context) -> dict:
    """Start OAuth flow for a storage connector."""
    provider = (args.get("provider") or "").strip().lower()
    if provider not in SUPPORTED_PROVIDERS:
        return _refuse("BAD_REQUEST",
                       f"unsupported provider {provider!r}; supported: {', '.join(SUPPORTED_PROVIDERS)}")
    matter_id = (args.get("matter_id") or "").strip()
    if not matter_id:
        return _refuse("BAD_REQUEST", "matter_id is required — files are scoped to a matter")

    if provider == "microsoft":
        from gateway.connectors.microsoft import authorize_url
        auth = authorize_url(actor_id=ctx.actor, matter_id=matter_id)
        # Store the verifier + matter_id keyed by state so callback can retrieve them.
        # The store method is a simple key-value write; the state expires after 10 minutes.
        if ctx.store is not None and hasattr(ctx.store, "write_connector_state"):
            ctx.store.write_connector_state(auth.state, {
                "provider": provider,
                "actor_id": ctx.actor,
                "matter_id": matter_id,
                "code_verifier": auth.code_verifier,
                "created_at": int(time.time()),
            })
        return {"status": "redirect", "url": auth.url, "state": auth.state,
                "code_verifier": auth.code_verifier}

    return _refuse("INTERNAL", "unreachable")


def _connectors_callback(args: dict, ctx: Context) -> dict:
    """Exchange OAuth authorization code for tokens."""
    provider = (args.get("provider") or "").strip().lower()
    code = (args.get("code") or "").strip()
    state = (args.get("state") or "").strip()
    code_verifier = (args.get("code_verifier") or "").strip()

    if not code:
        return _refuse("BAD_REQUEST", "authorization code is required")
    if provider not in SUPPORTED_PROVIDERS:
        return _refuse("BAD_REQUEST", f"unsupported provider {provider!r}")

    # Retrieve stored state if available.
    stored = None
    if ctx.store is not None and hasattr(ctx.store, "read_connector_state") and state:
        stored = ctx.store.read_connector_state(state)
        if stored:
            if stored["actor_id"] != ctx.actor:
                return _refuse("FORBIDDEN", "state does not belong to this actor")
            code_verifier = stored["code_verifier"]
            if int(time.time()) - stored["created_at"] > 600:
                return _refuse("BAD_REQUEST", "authorization state expired (10 min)")

    if not code_verifier:
        return _refuse("BAD_REQUEST", "code_verifier is required (from authorize step)")

    if provider == "microsoft":
        from gateway.connectors.microsoft import exchange_code
        try:
            tokens = exchange_code(code, code_verifier=code_verifier)
        except Exception as e:
            return _refuse("UPSTREAM", f"token exchange failed: {e}")

        matter_id = stored["matter_id"] if stored else (args.get("matter_id") or "").strip()
        if ctx.store is not None and hasattr(ctx.store, "write_connector_token"):
            ctx.store.write_connector_token({
                "provider": provider,
                "actor_id": ctx.actor,
                "matter_id": matter_id,
                "access_token": tokens["access_token"],
                "refresh_token": tokens["refresh_token"],
                "expires_at": tokens["expires_at"],
            })
        return {"status": "connected", "provider": provider,
                "expires_at": tokens["expires_at"]}

    return _refuse("INTERNAL", "unreachable")


def _get_access_token(provider: str, actor_id: str, matter_id: str, ctx: Context) -> str | None:
    """Retrieve a valid access token, refreshing if expired."""
    if ctx.store is None or not hasattr(ctx.store, "read_connector_token"):
        return None
    token_row = ctx.store.read_connector_token(provider=provider, actor_id=actor_id,
                                                matter_id=matter_id)
    if not token_row:
        return None
    if token_row["expires_at"] > int(time.time()) + 60:
        return token_row["access_token"]
    # Refresh.
    if provider == "microsoft":
        from gateway.connectors.microsoft import refresh_tokens
        try:
            new = refresh_tokens(token_row["refresh_token"])
        except Exception:
            return None
        if ctx.store is not None and hasattr(ctx.store, "write_connector_token"):
            ctx.store.write_connector_token({
                "provider": provider,
                "actor_id": actor_id,
                "matter_id": matter_id,
                "access_token": new["access_token"],
                "refresh_token": new["refresh_token"],
                "expires_at": new["expires_at"],
            })
        return new["access_token"]
    return None


def _connectors_list_files(args: dict, ctx: Context) -> dict:
    """List files from a connected storage provider."""
    provider = (args.get("provider") or "").strip().lower()
    matter_id = (args.get("matter_id") or "").strip()
    folder_id = (args.get("folder_id") or "").strip()
    query = (args.get("query") or "").strip()

    if provider not in SUPPORTED_PROVIDERS:
        return _refuse("BAD_REQUEST", f"unsupported provider {provider!r}")
    if not matter_id:
        return _refuse("BAD_REQUEST", "matter_id is required")

    access_token = _get_access_token(provider, ctx.actor, matter_id, ctx)
    if not access_token:
        return _refuse("NOT_CONNECTED",
                       f"no active {provider} connection for this matter. "
                       f"Use connectors.authorize first")

    if provider == "microsoft":
        from gateway.connectors.microsoft import (list_root, list_folder, search_files,
                                                   list_sharepoint_sites, list_site_drive_root)
        try:
            if query:
                items = search_files(query, access_token=access_token)
            elif folder_id:
                items = list_folder(folder_id, access_token=access_token)
            else:
                items = list_root(access_token=access_token)
        except Exception as e:
            return _refuse("UPSTREAM", f"Graph API error: {e}")

        return {"status": "ok", "provider": provider, "count": len(items),
                "files": [{"id": i.id, "name": i.name, "path": i.path,
                           "size": i.size, "mime_type": i.mime_type,
                           "is_folder": i.is_folder, "modified": i.modified,
                           "web_url": i.web_url} for i in items]}

    return _refuse("INTERNAL", "unreachable")


def _connectors_import_file(args: dict, ctx: Context) -> dict:
    """Download a file from connected storage and add it to the matter vault."""
    provider = (args.get("provider") or "").strip().lower()
    matter_id = (args.get("matter_id") or "").strip()
    file_id = (args.get("file_id") or "").strip()
    file_name = (args.get("file_name") or "").strip()

    if provider not in SUPPORTED_PROVIDERS:
        return _refuse("BAD_REQUEST", f"unsupported provider {provider!r}")
    if not matter_id:
        return _refuse("BAD_REQUEST", "matter_id is required")
    if not file_id:
        return _refuse("BAD_REQUEST", "file_id is required")

    access_token = _get_access_token(provider, ctx.actor, matter_id, ctx)
    if not access_token:
        return _refuse("NOT_CONNECTED",
                       f"no active {provider} connection for this matter")

    if provider == "microsoft":
        from gateway.connectors.microsoft import download_file
        try:
            content = download_file(file_id, access_token=access_token)
        except Exception as e:
            return _refuse("UPSTREAM", f"download failed: {e}")

        if len(content) > MAX_FILE_SIZE:
            return _refuse("BAD_REQUEST",
                           f"file is {len(content) / 1024 / 1024:.1f} MB, "
                           f"max is {MAX_FILE_SIZE / 1024 / 1024:.0f} MB")

        sha256 = hashlib.sha256(content).hexdigest()

        # Store in vault if store available.
        if ctx.store is not None and hasattr(ctx.store, "write_vault_document"):
            import uuid
            doc = {
                "document_id": str(uuid.uuid4()),
                "matter_id": matter_id,
                "name": file_name or f"imported-{file_id[:8]}",
                "sha256": sha256,
                "size": len(content),
                "source": f"{provider}:{file_id}",
                "uploaded_by": ctx.actor,
            }
            try:
                ctx.store.write_vault_document(doc)
            except Exception as e:
                return _refuse("STORE", f"vault write failed: {e}")
            return {"status": "imported", "document_id": doc["document_id"],
                    "sha256": sha256, "size": len(content), "name": doc["name"]}

        return {"status": "downloaded", "sha256": sha256, "size": len(content),
                "name": file_name or file_id}

    return _refuse("INTERNAL", "unreachable")


# ── self-test ────────────────────────────────────────────────────────────────

def _test() -> None:
    import os
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    print("connectors verbs")

    # Fake context with no store.
    class _Ctx:
        actor = "test-actor"
        store = None
    ctx = _Ctx()

    # authorize — bad provider
    r = _connectors_authorize({"provider": "dropbox"}, ctx)
    check(r.get("code") == "BAD_REQUEST", f"bad provider refused ({r.get('code')})")

    # authorize — missing matter
    r = _connectors_authorize({"provider": "microsoft"}, ctx)
    check(r.get("code") == "BAD_REQUEST" and "matter_id" in r.get("detail", ""),
          "missing matter_id refused")

    # authorize — happy path (needs env)
    os.environ["MS_CLIENT_ID"] = "test-id"
    os.environ["MS_CLIENT_SECRET"] = "test-secret"
    os.environ["MS_REDIRECT_URI"] = "https://localhost/cb"
    try:
        r = _connectors_authorize({"provider": "microsoft", "matter_id": "m-1"}, ctx)
        check(r.get("status") == "redirect" and "test-id" in r.get("url", ""),
              f"authorize returns redirect URL ({r.get('status')})")
        check("code_verifier" in r, "code_verifier returned for client to store")
    finally:
        del os.environ["MS_CLIENT_ID"]
        del os.environ["MS_CLIENT_SECRET"]
        del os.environ["MS_REDIRECT_URI"]

    # callback — missing code
    r = _connectors_callback({"provider": "microsoft"}, ctx)
    check(r.get("code") == "BAD_REQUEST", "callback without code refused")

    # list_files — not connected
    r = _connectors_list_files({"provider": "microsoft", "matter_id": "m-1"}, ctx)
    check(r.get("code") == "NOT_CONNECTED", f"list without connection refused ({r.get('code')})")

    # import — not connected
    r = _connectors_import_file({"provider": "microsoft", "matter_id": "m-1", "file_id": "f-1"}, ctx)
    check(r.get("code") == "NOT_CONNECTED", "import without connection refused")

    # import — missing file_id
    r = _connectors_import_file({"provider": "microsoft", "matter_id": "m-1"}, ctx)
    check(r.get("code") == "BAD_REQUEST" and "file_id" in r.get("detail", ""),
          "import without file_id refused")

    # SUPPORTED_PROVIDERS safety
    check(all(p in ("microsoft",) for p in SUPPORTED_PROVIDERS),
          "only microsoft is supported (no premature additions)")

    # MAX_FILE_SIZE
    check(MAX_FILE_SIZE == 50 * 1024 * 1024, "50 MB file limit")

    print(f"\n{ok + fail}/{ok + fail} run, {ok} passed, {fail} failed")
    if fail:
        sys.exit(1)


if __name__ == "__main__":
    _test()
