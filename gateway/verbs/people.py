"""Sign-in, sessions and invites (026); the firm's people and pending invites (036)."""
from __future__ import annotations

from gateway.verbs.core import Context, _refuse


# ── 026: sign-in, sessions, invites ──────────────────────────────────────────
#
# auth.login and invites.accept are PUBLIC_VERBS (gateway/roles.py): app.py mounts them
# with no Bearer token and no role check, so `ctx.store` is None and `ctx.auth` /
# `ctx.backend_for` carry what they need instead -- the cross-tenant lookup, and a
# factory for the tenant-scoped backend once the lookup has named a tenant. See
# DECISION_ACCOUNTS.md and gateway/migrations/026_accounts.sql.

def _future(seconds: int):
    """now + seconds, timezone-aware. The one place session and invite TTLs compute from."""
    from datetime import datetime, timedelta, timezone
    return datetime.now(timezone.utc) + timedelta(seconds=seconds)


def _auth_login(args: dict, ctx: Context) -> dict:
    """Sign in by email and password. PUBLIC.

    Wrong password, unknown email, a disabled account and an un-accepted invite (which
    has no `actors` row yet, so it IS an unknown email) all return
    `accounts.generic_failure()` -- byte-identical, so none is distinguishable from
    outside (DECISION_ACCOUNTS.md Decision 6). More than one match across tenants is the
    ambiguous-email case (Decision 7): refused the same way, never guessed.
    """
    from gateway import accounts
    from gateway.auth import hash_key
    email = str(args.get("email") or "").strip()
    password = str(args.get("password") or "")
    if not email or not password:
        return _refuse("BAD_REQUEST", "email and password are both required")
    if ctx.auth is None:
        return _refuse("NO_STORE", "no auth backend is configured")

    email_hash = hash_key(email.lower())
    # No known client address (the trusted proxy could not name one): count this attempt
    # against the email only. A fixed placeholder would put every such sign-in into one
    # shared bucket -- the whole team locked out by one person's typos. A random hash
    # matches no other row, so only the per-email count can ever reach its line.
    import secrets
    ip_hash = hash_key(ctx.client_ip) if ctx.client_ip else secrets.token_hex(32)
    locked = accounts.check_lockout(ctx.auth, email_hash=email_hash, ip_hash=ip_hash)
    if locked is not None:
        return locked

    rows = ctx.auth.find_logins(email)
    if len(rows) != 1:
        accounts.verify_login(None, password)   # pays the same cost as a real check
        ctx.auth.record_attempt(email_hash=email_hash, ip_hash=ip_hash, ok=False)
        return accounts.generic_failure()

    row = rows[0]
    if not accounts.verify_login(row, password) or row.get("disabled_at") is not None:
        ctx.auth.record_attempt(email_hash=email_hash, ip_hash=ip_hash, ok=False)
        return accounts.generic_failure()

    if ctx.backend_for is None:
        return _refuse("NO_STORE", "no tenant store factory is configured")
    import uuid
    tenant_id, actor_id = row["tenant_id"], row["actor_id"]
    store = ctx.backend_for(tenant_id, actor_id)
    raw_token, token_hash = accounts.mint_token()
    expires_at = _future(accounts.SESSION_TTL_SECONDS)
    store.create_session({"session_id": str(uuid.uuid4()), "actor_id": actor_id,
                          "token_hash": token_hash, "expires_at": expires_at})
    actor_row = store.read_actor(actor_id) or {}
    ctx.auth.record_attempt(email_hash=email_hash, ip_hash=ip_hash, ok=True)
    return {"status": "ok", "token": raw_token, "actor_id": actor_id,
            "tenant_id": tenant_id, "role": actor_row.get("role") or "viewer",
            "expires_at": str(expires_at)}


def _auth_logout(args: dict, ctx: Context) -> dict:
    """End the CALLER'S OWN session. Needs a Bearer (not public); routed normally."""
    if not ctx.credential_hash:
        return _refuse("BAD_REQUEST", "this credential is not a session; there is "
                       "nothing for auth.logout to revoke")
    if ctx.store is None:
        return _refuse("NO_STORE", "no store is configured")
    revoked = ctx.store.revoke_session(ctx.credential_hash)
    return {"status": "ok", "revoked": revoked}


def _auth_me(args: dict, ctx: Context) -> dict:
    """Who the caller is. Always the caller's OWN row; there is no argument that names
    somebody else's."""
    if ctx.store is None:
        return _refuse("NO_STORE", "no store is configured")
    actor = ctx.store.read_actor(ctx.actor) or {}
    return {"actor_id": ctx.actor, "tenant_id": ctx.tenant, "email": actor.get("email"),
            "role": actor.get("role") or "viewer", "label": actor.get("label") or ""}


def _invites_create(args: dict, ctx: Context) -> dict:
    """Invite someone into this firm. ADMIN-only (gateway/roles.py): "admin: everything a
    lawyer can, plus invite and remove people." The raw token is returned ONCE, to be
    shared out of band, and is never stored -- only its hash is (018_users_roles.sql)."""
    from gateway.roles import ROLES
    if ctx.store is None:
        return _refuse("NO_STORE", "no store is configured")
    email = str(args.get("email") or "").strip()
    role = str(args.get("role") or "").strip()
    if not email or "@" not in email[1:]:
        return _refuse("BAD_REQUEST", "a real email address is required")
    if role not in ROLES:
        return _refuse("BAD_REQUEST", f"role must be one of {ROLES}")
    import uuid

    from gateway import accounts
    # One account per email per firm: an invite to an email that already has one could
    # only fail at accept, after the invitee chose a password.
    if ctx.store.find_actor_by_email(email):
        return _refuse("CONFLICT", "An account with this email already exists in this firm.")
    # One sign-in per email across ALL firms (033): a second one would make auth.login
    # refuse both, so another firm could lock this person out. Which firm is not said.
    if ctx.auth is not None and any(r.get("tenant_id") != ctx.tenant
                                    for r in ctx.auth.find_logins(email)):
        return _refuse("CONFLICT", "This email already has a sign-in with another "
                                   "organisation. Please invite a different email.")
    raw_token, token_hash = accounts.mint_token()
    try:
        row = ctx.store.create_invite({
            "invite_id": str(uuid.uuid4()), "email": email, "role": role,
            "token_hash": token_hash, "invited_by": ctx.actor,
            "expires_at": _future(accounts.INVITE_TTL_SECONDS)})
    except Exception as e:                                       # noqa: BLE001
        return _refuse("BAD_REQUEST", str(e)[:200])
    return dict(row, token=raw_token,
               note="Share this token with the invitee out of band. It is shown once "
                    "here and is never stored -- only its hash is.")


def _invites_accept(args: dict, ctx: Context) -> dict:
    """Spend a single-use invite token and create the account it names. PUBLIC.

    role and email come from the INVITE, never from this request -- accepting an invite
    must not let the acceptor choose their own role.
    """
    from gateway import accounts
    from gateway.auth import hash_key
    from gateway.passwords import PasswordError, hash_password
    token = str(args.get("token") or "").strip()
    password = str(args.get("password") or "")
    if not token or not password:
        return _refuse("BAD_REQUEST", "token and password are both required")
    if ctx.auth is None:
        return _refuse("NO_STORE", "no auth backend is configured")

    token_hash = hash_key(token)
    invite = ctx.auth.find_invite(token_hash)
    if invite is None or invite.get("accepted_at") is not None:
        return _refuse("INVALID_INVITE",
                       "this invite link is not valid or has already been used")

    try:
        pw_hash = hash_password(password)
    except PasswordError as e:
        return _refuse("BAD_REQUEST", str(e))

    if ctx.backend_for is None:
        return _refuse("NO_STORE", "no tenant store factory is configured")
    import uuid
    from datetime import datetime, timezone
    new_actor_id = str(uuid.uuid4())
    store = ctx.backend_for(invite["tenant_id"], new_actor_id)
    # The single-use AND expiry guarantees both live in accept_invite's own atomic
    # UPDATE (gateway/store.py) -- "accepted_at IS NULL AND expires_at > now()" -- not in
    # this handler, so a concurrent accept of the same token cannot both win.
    from gateway.store import StoreError
    try:
        accepted = store.accept_invite(token_hash, actor_id=new_actor_id,
                                       now=str(datetime.now(timezone.utc)),
                                       actor={"label": invite["email"], "role": invite["role"],
                                              "email": invite["email"],
                                              "password_hash": pw_hash})
    except StoreError:
        # The account could not be created (an account with this email appeared after the
        # invite was issued). The transaction rolled back and the invite is unspent; the
        # answer is the same one every other unusable token gets.
        accepted = None
    if accepted is None:
        return _refuse("INVALID_INVITE",
                       "this invite link is not valid or has already been used")
    return {"status": "accepted", "actor_id": new_actor_id,
            "tenant_id": invite["tenant_id"], "role": invite["role"]}


# ── 036: the firm's people and its pending invites (Team page) ───────────────
# All three are ADMIN (gateway/roles.py) and read or write ONLY through ctx.store, which
# is bound to the caller's tenant: on Postgres, RLS (tenant_isolation on actors and
# invites) is what keeps another firm's rows out, whatever id is passed.

def _people_list(args: dict, ctx: Context) -> dict:
    """Everyone in this firm who signs in by email: name, email, role, when they joined.
    Never a password hash or a session."""
    if ctx.store is None:
        return _refuse("NO_STORE", "no store is configured")
    return {"people": [{"actor_id": a["actor_id"], "name": a.get("label") or "",
                        "email": a.get("email"), "role": a.get("role") or "viewer",
                        "joined_at": a.get("created_at"),
                        "disabled": a.get("disabled_at") is not None}
                       for a in ctx.store.list_actors()]}


def _invites_list(args: dict, ctx: Context) -> dict:
    """Invites not yet accepted, cancelled or expired. Never the token or its hash: the
    raw token was shown once at invites.create and exists nowhere else."""
    if ctx.store is None:
        return _refuse("NO_STORE", "no store is configured")
    return {"invites": [{k: i.get(k) for k in ("invite_id", "email", "role", "invited_by",
                                                "created_at", "expires_at")}
                        for i in ctx.store.list_pending_invites()]}


def _invites_cancel(args: dict, ctx: Context) -> dict:
    """Withdraw an unused invite. The row is marked, never deleted; accepting it afterwards
    gets the same INVALID_INVITE as any other unusable token."""
    if ctx.store is None:
        return _refuse("NO_STORE", "no store is configured")
    invite_id = str(args.get("invite_id") or "").strip()
    if not invite_id:
        return _refuse("BAD_REQUEST", "invite_id required")
    if not ctx.store.cancel_invite(invite_id, cancelled_by=ctx.actor):
        # Unknown, another firm's, already used or already cancelled: one answer, so an id
        # cannot be probed to learn which.
        return _refuse("NOT_FOUND", "There is no pending invite with that id in this firm.")
    return {"status": "cancelled", "invite_id": invite_id}
