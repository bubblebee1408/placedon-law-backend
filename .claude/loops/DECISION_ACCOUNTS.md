# DECISION — Personal accounts (sign-in, sessions, invites, user management)

- **Status:** PROPOSED
- **Date:** 2026-10-14
- **Branch:** `claude/accounts` (cut from `main` @ 82b70d1)
- **Supersedes nothing.** API keys keep working exactly as they do; this is additive.

## Context

`actors` already carries `role`/`email`/`password_hash`/`disabled_at` (018), the `invites`
table exists with RLS + a single-use token hash, scrypt lives in `gateway/passwords.py`, the
three ordered roles live in `gateway/roles.py`, and `gateway/auth.py` resolves an **API key**
to a `Principal` from an in-memory `KeyStore`. What is missing is everything a *person* needs:
a way to sign in, a session that survives a restart and can be revoked, invites as verbs, and
user management. `app.py:_principal()` is the single place a `Bearer` token becomes a
`Principal`, and `app.py` `_mount/_route` is the single place a role is checked.

## The hard problem: authentication precedes tenant knowledge

Every tenant-scoped table is isolated by `current_setting('app.tenant_id')` under FORCE RLS.
But at sign-in we have only an **email**, and when a session token arrives we have only the
**token** — the tenant is not known yet, so RLS cannot be set, so a normal query returns
nothing. Two reads therefore must cross tenants. They are the only ones.

### Decision 1 — `auth_find_login(email text)` : SECURITY DEFINER

Returns, for each `actors` row whose `lower(email)` matches **and whose `password_hash` is
not null**, exactly these columns and no others:

    actor_id uuid, tenant_id uuid, password_hash text, disabled_at timestamptz

- `SECURITY DEFINER`, `search_path = pg_catalog, public` pinned in the definition (so a
  caller cannot shadow a table/function it uses).
- **Why it is safe:** it exposes no tenant *content* — only an actor's id, its tenant, its
  stored scrypt hash (already one-way and useless without the password), and whether it is
  disabled. It is keyed on one supplied email, returns nothing for an unknown one, and the
  caller turns every outcome into one generic failure (Decision 6), so it enables no
  enumeration. It is the minimum a password check needs and nothing a logged-in user could
  not already learn about their own row.
- **Ambiguity (Decision 7):** `actors` is unique on `(tenant_id, lower(email))` but an email
  may exist in two tenants. If the function returns **more than one** row with a password,
  `auth.login` refuses with the *same generic failure*, records the event (metadata-only
  audit), and does not guess a tenant. A `research/TASKS.md` row tracks the real fix
  (tenant-qualified sign-in / an org picker).

### Decision 2 — `auth_resolve_session(token_hash text)` : SECURITY DEFINER

Returns at most one row, exactly these columns:

    actor_id uuid, tenant_id uuid, role text, expires_at timestamptz,
    revoked_at timestamptz, disabled_at timestamptz

(`disabled_at` joined from `actors`, so a disabled user's live session is refused without a
second round trip.)

- `SECURITY DEFINER`, pinned `search_path`. Lookup is by `sha256(token)` — 256 bits of
  entropy from `secrets.token_urlsafe(32)`, so there is nothing to guess and a timing side
  channel buys nothing.
- **Why it is safe:** it returns only session-identity columns (no `token_hash`, never the
  token, no tenant content). The middleware (Decision 3) decides validity — expired, revoked,
  or disabled all become **401**, never an empty result that could read as "no data."

### Decision 3 — one `Principal`, two sources, key first

`app.py:_principal()` tries the `Bearer` value as an **API key** (`KeyStore.resolve`) first;
on `AuthError` it tries it as a **session** (`auth_resolve_session(sha256(token))`). Either
way the request becomes the same `Principal(tenant_id, actor, key_id, label, role)` — a
session carries `label="session"` and `key_id` = the session id prefix (never the token). An
expired/revoked/disabled session raises `AuthError` → 401. API-key behaviour is unchanged.

### Decision 4 — these two functions are the only cross-tenant reads of tenant data

Everything else stays tenant-scoped under the existing RLS: creating a session (after
`auth_find_login` yields the tenant, set `app.tenant_id` and insert normally), logout, `me`,
invites.create/accept, and all user management run with a known tenant.

### Decision 5 — the two new tables

- **`sessions`** is tenant-scoped (has `tenant_id`, FORCE RLS, `tenant_isolation` policy like
  every other table). Writes happen with the tenant known; the only tenant-blind read is the
  definer function above.
- **`login_attempts`** is deliberately **not** tenant-scoped — its columns are `email_hash`,
  `ip_hash`, `at`, `ok`, and nothing else. Brute-force defence must count failures for an
  email/IP *before* any tenant is known and across all tenants, so a tenant column would
  defeat its purpose. It still gets FORCE RLS, with an explicit `USING (true)` policy that
  says "no row restriction, on purpose": it holds only one-way hashes, no tenant content, so
  there is nothing to isolate and a global count is the security property we want. This is not
  a cross-tenant read of tenant data — there is no tenant data in it.

### Decision 6 — the two no-key verbs are `PUBLIC_VERBS`

`auth.login` and `invites.accept` run with no `Bearer` token, so `app.py` skips `_principal`
and the `may()` check for them, and `roles.py` keeps them in a `PUBLIC_VERBS` set that its
exhaustiveness test excludes from `REQUIRED` (so "every other verb declares a role" stays
true and these two are not silently handed a role they bypass anyway).

- `auth.login` is safe public: wrong password, unknown email, disabled account and
  un-accepted invite return one byte-identical failure; an unknown email still runs
  `verify_password` against a dummy hash so timing does not reveal it; 5 failures per
  email-or-IP in 15 minutes → `LOCKED_OUT` with `retry_after`.
- `invites.accept` is safe public: it requires a single-use, unguessable token
  (`sha256` lookup, partial-unique "one live invite per email per tenant"), sets the new
  password (≥12), and the token is spent atomically on accept.

Every call (public ones included) still writes the usual **metadata-only** audit row. No
password, token or hash ever reaches a log, audit row or error message.

## Reversal condition

Revert if any of these becomes true:
1. A security review shows either definer function can return a column not listed above, or
   can be driven to leak tenant content, and it cannot be fixed by narrowing the function.
2. The ambiguous-email path (Decision 7) is ever observed selecting a tenant instead of
   refusing.
3. `login_attempts`'s `USING (true)` policy is found to expose anything beyond one-way hashes.

**Reversal is clean:** sessions and accounts are additive. Drop migration 026 (both tables +
both functions), remove `PUBLIC_VERBS` and the session branch in `_principal`, and the system
is back to API-keys-only with no legal data lost — nothing in the corpus, runs, or audit
chain depends on a session existing.
