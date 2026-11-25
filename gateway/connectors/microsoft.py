"""Microsoft Graph connector — OAuth2 + SharePoint/OneDrive file access.

No third-party HTTP library: urllib.request only, matching the rest of the codebase.
Tokens are opaque dicts {access_token, refresh_token, expires_at} — the store
encrypts them, this module never writes them to disk.

Security invariants:
- Read-only: Files.Read.All scope, never Files.ReadWrite.
- state parameter ties the OAuth round-trip to the actor + matter.
- PKCE (S256) prevents authorization code interception.
- Tokens are per-actor, per-tenant; no cross-tenant file access.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

AUTHORITY = "https://login.microsoftonline.com/common"
GRAPH_BASE = "https://graph.microsoft.com/v1.0"
# Read-only. Never request write scopes.
SCOPES = "Files.Read.All Sites.Read.All offline_access"


def _env(name: str) -> str:
    v = os.environ.get(name, "").strip()
    if not v:
        raise RuntimeError(f"{name} is not set")
    return v


def client_id() -> str:
    return _env("MS_CLIENT_ID")


def client_secret() -> str:
    return _env("MS_CLIENT_SECRET")


def redirect_uri() -> str:
    return _env("MS_REDIRECT_URI")


# ── PKCE ─────────────────────────────────────────────────────────────────────

def pkce_pair() -> tuple[str, str]:
    """(code_verifier, code_challenge) for S256 PKCE."""
    verifier = secrets.token_urlsafe(96)[:128]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    import base64
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


# ── OAuth2 authorization code flow ───────────────────────────────────────────

@dataclass(frozen=True)
class AuthStart:
    """Returned to the caller so it can redirect the user's browser."""
    url: str
    state: str
    code_verifier: str  # store this server-side, keyed by state


def authorize_url(*, actor_id: str, matter_id: str) -> AuthStart:
    """Build the Microsoft authorization URL for a user to visit."""
    verifier, challenge = pkce_pair()
    state = hashlib.sha256(
        f"{actor_id}:{matter_id}:{secrets.token_hex(16)}".encode()
    ).hexdigest()[:32]
    params = {
        "client_id": client_id(),
        "response_type": "code",
        "redirect_uri": redirect_uri(),
        "scope": SCOPES,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "prompt": "consent",
    }
    url = f"{AUTHORITY}/oauth2/v2.0/authorize?" + urllib.parse.urlencode(params)
    return AuthStart(url=url, state=state, code_verifier=verifier)


def exchange_code(code: str, *, code_verifier: str) -> dict:
    """Exchange an authorization code for tokens. Returns {access_token, refresh_token, expires_at}."""
    data = urllib.parse.urlencode({
        "client_id": client_id(),
        "client_secret": client_secret(),
        "code": code,
        "redirect_uri": redirect_uri(),
        "grant_type": "authorization_code",
        "code_verifier": code_verifier,
    }).encode()
    req = urllib.request.Request(
        f"{AUTHORITY}/oauth2/v2.0/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = json.loads(resp.read())
    return {
        "access_token": body["access_token"],
        "refresh_token": body.get("refresh_token", ""),
        "expires_at": int(time.time()) + body.get("expires_in", 3600),
    }


def refresh_tokens(refresh_token: str) -> dict:
    """Use a refresh token to get a new access token."""
    data = urllib.parse.urlencode({
        "client_id": client_id(),
        "client_secret": client_secret(),
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
        "scope": SCOPES,
    }).encode()
    req = urllib.request.Request(
        f"{AUTHORITY}/oauth2/v2.0/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = json.loads(resp.read())
    return {
        "access_token": body["access_token"],
        "refresh_token": body.get("refresh_token", refresh_token),
        "expires_at": int(time.time()) + body.get("expires_in", 3600),
    }


# ── Graph API helpers ────────────────────────────────────────────────────────

def _graph_get(path: str, *, access_token: str, params: dict | None = None) -> Any:
    url = f"{GRAPH_BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def _graph_download(path: str, *, access_token: str) -> bytes:
    url = f"{GRAPH_BASE}{path}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {access_token}",
    })
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


# ── File operations ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class DriveItem:
    id: str
    name: str
    path: str
    size: int
    mime_type: str
    is_folder: bool
    modified: str
    web_url: str


def _to_item(raw: dict) -> DriveItem:
    return DriveItem(
        id=raw["id"],
        name=raw.get("name", ""),
        path=raw.get("parentReference", {}).get("path", "") + "/" + raw.get("name", ""),
        size=raw.get("size", 0),
        mime_type=raw.get("file", {}).get("mimeType", "folder" if "folder" in raw else "unknown"),
        is_folder="folder" in raw,
        modified=raw.get("lastModifiedDateTime", ""),
        web_url=raw.get("webUrl", ""),
    )


def list_root(*, access_token: str) -> list[DriveItem]:
    """List files in the user's OneDrive root."""
    data = _graph_get("/me/drive/root/children",
                      access_token=access_token,
                      params={"$top": "50", "$select": "id,name,size,file,folder,parentReference,lastModifiedDateTime,webUrl"})
    return [_to_item(item) for item in data.get("value", [])]


def list_folder(folder_id: str, *, access_token: str) -> list[DriveItem]:
    """List children of a folder."""
    data = _graph_get(f"/me/drive/items/{folder_id}/children",
                      access_token=access_token,
                      params={"$top": "50", "$select": "id,name,size,file,folder,parentReference,lastModifiedDateTime,webUrl"})
    return [_to_item(item) for item in data.get("value", [])]


def search_files(query: str, *, access_token: str) -> list[DriveItem]:
    """Search files by name across the user's drive."""
    data = _graph_get(f"/me/drive/root/search(q='{urllib.parse.quote(query)}')",
                      access_token=access_token,
                      params={"$top": "25", "$select": "id,name,size,file,folder,parentReference,lastModifiedDateTime,webUrl"})
    return [_to_item(item) for item in data.get("value", [])]


def download_file(item_id: str, *, access_token: str) -> bytes:
    """Download a file's content by its drive item ID."""
    return _graph_download(f"/me/drive/items/{item_id}/content", access_token=access_token)


def list_sharepoint_sites(*, access_token: str, query: str = "") -> list[dict]:
    """Search SharePoint sites. Returns [{id, name, webUrl}]."""
    path = "/sites" if not query else f"/sites?search={urllib.parse.quote(query)}"
    data = _graph_get(path, access_token=access_token)
    return [{"id": s["id"], "name": s.get("displayName", ""), "webUrl": s.get("webUrl", "")}
            for s in data.get("value", [])]


def list_site_drive_root(site_id: str, *, access_token: str) -> list[DriveItem]:
    """List files in a SharePoint site's default document library."""
    data = _graph_get(f"/sites/{site_id}/drive/root/children",
                      access_token=access_token,
                      params={"$top": "50", "$select": "id,name,size,file,folder,parentReference,lastModifiedDateTime,webUrl"})
    return [_to_item(item) for item in data.get("value", [])]


# ── self-test ────────────────────────────────────────────────────────────────

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

    print("microsoft connector")

    # PKCE pair
    v, c = pkce_pair()
    check(len(v) == 128 and len(c) > 20, f"PKCE: verifier length {len(v)}, challenge length {len(c)}")
    # S256 roundtrip
    import base64
    digest = hashlib.sha256(v.encode("ascii")).digest()
    expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    check(c == expected, "PKCE S256 roundtrip")

    # authorize_url (needs env vars — test with fakes)
    os.environ["MS_CLIENT_ID"] = "test-client-id"
    os.environ["MS_CLIENT_SECRET"] = "test-secret"
    os.environ["MS_REDIRECT_URI"] = "https://localhost/callback"
    try:
        auth = authorize_url(actor_id="actor-1", matter_id="matter-1")
        check("test-client-id" in auth.url, "authorize URL contains client_id")
        check("code_challenge=" in auth.url, "authorize URL contains PKCE challenge")
        check("S256" in auth.url, "authorize URL uses S256")
        check("Files.Read.All" in auth.url, "scopes are read-only")
        check("Files.ReadWrite" not in auth.url, "no write scopes")
        check(len(auth.state) == 32, f"state is 32 hex chars ({len(auth.state)})")
        check(len(auth.code_verifier) == 128, "code_verifier is stored for callback")
    finally:
        del os.environ["MS_CLIENT_ID"]
        del os.environ["MS_CLIENT_SECRET"]
        del os.environ["MS_REDIRECT_URI"]

    # DriveItem construction
    raw = {"id": "abc", "name": "test.pdf", "size": 1024,
           "file": {"mimeType": "application/pdf"},
           "parentReference": {"path": "/drive/root:"},
           "lastModifiedDateTime": "2026-01-01T00:00:00Z", "webUrl": "https://example.com"}
    item = _to_item(raw)
    check(item.name == "test.pdf" and item.mime_type == "application/pdf",
          "DriveItem from raw dict")
    check(not item.is_folder, "file is not folder")
    check(item.size == 1024, "size preserved")

    raw_folder = {"id": "def", "name": "Legal", "size": 0,
                  "folder": {"childCount": 3},
                  "parentReference": {"path": "/drive/root:"},
                  "lastModifiedDateTime": "2026-01-01T00:00:00Z", "webUrl": "https://example.com"}
    folder = _to_item(raw_folder)
    check(folder.is_folder and folder.mime_type == "folder", "folder detected")

    # scope safety
    check("ReadWrite" not in SCOPES, "SCOPES constant has no write permission")
    check("offline_access" in SCOPES, "offline_access for refresh tokens")

    print(f"\n{ok + fail}/{ok + fail} run, {ok} passed, {fail} failed")
    if fail:
        sys.exit(1)


if __name__ == "__main__":
    _test()
