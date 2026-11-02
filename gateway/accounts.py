#!/usr/bin/env python3
"""The business logic behind `auth.login` and `invites.accept`: generic failure, lockout,
timing-safe verification against an unknown email, and token minting.

Kept out of gateway/verbs.py (already the largest module in the gateway) because this is
exactly the kind of focused, security-sensitive logic that is easiest to review and test in
its own small file -- lockout math, the dummy-hash timing guard, and the byte-identical
generic failure are each a handful of lines with a reason, not a handler's worth of
plumbing.

## The generic failure (DECISION_ACCOUNTS.md Decision 6)

Wrong password, unknown email, a disabled account and an un-accepted invite all return ONE
byte-identical refusal. "Un-accepted invite" needs no special case: before `invites.accept`
runs, that person has no `actors` row at all, so they fall out of `find_logins` exactly like
any other unknown email.

## Why an unknown email still pays the password-hashing cost

If an unknown email returned instantly and a known one spent ~100ms in scrypt, the response
time alone would tell an attacker which emails exist -- a timing side channel that needs no
error message to work. `verify_login` runs `passwords.verify_password` against a REAL scrypt
hash either way (`_dummy_hash()`, computed once per process); the row argument decides only
whether the computed result is allowed to matter, never whether the computation happens.

Run: PYTHONPATH=. python3 gateway/accounts.py
"""
from __future__ import annotations

import datetime as _dt
import functools
import re

__all__ = ["GENERIC_LOGIN_FAILURE_CODE", "LOGIN_LOCKOUT_MAX", "LOGIN_LOCKOUT_IP_MAX",
           "LOGIN_LOCKOUT_WINDOW_SECONDS",
           "SESSION_TTL_SECONDS", "INVITE_TTL_SECONDS", "generic_failure", "verify_login",
           "check_lockout", "mint_token"]

# 5 failures per EMAIL in 15 minutes -- DECISION_ACCOUNTS.md Decision 6, unchanged.
LOGIN_LOCKOUT_MAX = 5
# Per client ADDRESS the line is higher, so one office behind one NAT address is not locked
# out by one person's typos (OWASP Authentication / Credential Stuffing Prevention cheat
# sheets: throttle per account AND per source, the source limit looser). 30 still stops one
# address cycling through emails: six accounts' worth of guesses, then it waits.
LOGIN_LOCKOUT_IP_MAX = 30
LOGIN_LOCKOUT_WINDOW_SECONDS = 15 * 60

# Session lifetime: 7 days (founder's call 2026-10-15 -- longer, so testing doesn't force a
# re-sign-in mid-flow). Easy to change in one place. Invites stay at 7 days.
SESSION_TTL_SECONDS = 7 * 24 * 60 * 60
INVITE_TTL_SECONDS = 7 * 24 * 60 * 60

GENERIC_LOGIN_FAILURE_CODE = "INVALID_CREDENTIALS"


def generic_failure() -> dict:
    """A FRESH dict every call -- coding-style.md's immutability rule: never hand out a
    shared mutable object a caller might (and in this codebase, several callers do)
    attach extra fields to before returning it as a verb's envelope."""
    return {"status": "REFUSED", "code": GENERIC_LOGIN_FAILURE_CODE,
            "detail": "incorrect email or password."}


@functools.lru_cache(maxsize=1)
def _dummy_hash() -> str:
    """A real scrypt hash of a fixed, non-secret string, computed ONCE per process.

    Not a secret and not a credential for any real account -- its only job is to make
    `passwords.verify_password` pay its real cost when the email is unknown.
    """
    from gateway import passwords
    return passwords.hash_password("placedon-dummy-hash-no-account-has-this-password")


def verify_login(row: dict | None, password: str) -> bool:
    """True only when `row` is a real actor AND `password` matches its stored hash.

    Always runs `passwords.verify_password`, on `row`'s hash when there is one and on
    `_dummy_hash()` when there is not, so the cost paid is identical either way. The
    `bool(row) and ...` guard is deliberate and tested at its own edge: if an attacker's
    guess happened to equal the dummy string, `matched` would be True, and this is what
    stops that from ever being treated as a real login.
    """
    from gateway import passwords
    stored = (row or {}).get("password_hash") or _dummy_hash()
    matched = passwords.verify_password(password, stored)
    return bool(row) and matched


def check_lockout(auth, *, email_hash: str, ip_hash: str,
                  now: _dt.datetime | None = None) -> dict | None:
    """A LOCKED_OUT refusal, or None. Counts failures for the email and for the IP
    SEPARATELY, in the last LOGIN_LOCKOUT_WINDOW_SECONDS, across every tenant --
    `login_attempts` has no tenant column, by design (DECISION_ACCOUNTS.md Decision 5):
    brute-force defence must span tenants and run before any tenant is known. Locked when
    the email reaches LOGIN_LOCKOUT_MAX or the IP reaches LOGIN_LOCKOUT_IP_MAX; the
    refusal is the same either way, so it does not say which one tripped.
    """
    now = now or _dt.datetime.now(_dt.timezone.utc)
    since = now - _dt.timedelta(seconds=LOGIN_LOCKOUT_WINDOW_SECONDS)
    by_email, by_ip = auth.recent_failures(email_hash=email_hash, ip_hash=ip_hash, since=since)
    if by_email < LOGIN_LOCKOUT_MAX and by_ip < LOGIN_LOCKOUT_IP_MAX:
        return None
    return {"status": "REFUSED", "code": "LOCKED_OUT",
            "detail": "too many failed sign-in attempts. Try again shortly.",
            "retry_after": LOGIN_LOCKOUT_WINDOW_SECONDS}


def mint_token() -> tuple[str, str]:
    """(raw, sha256-hash) -- 256 random bits, the same shape api_keys and invites already
    use. gateway/auth.py's own reasoning applies unchanged: nothing to guess, so a fast
    hash is safe, and the raw value is returned to the caller exactly once."""
    import secrets

    from gateway.auth import hash_key
    raw = secrets.token_urlsafe(32)
    return raw, hash_key(raw)


# The exact shape mint_token produces: token_urlsafe(32) is always 43 urlsafe-base64 chars.
_TOKEN_SHAPE = re.compile(r"[A-Za-z0-9_-]{43}")


def is_token_shaped(raw: str | None) -> bool:
    """Could `raw` be a session token mint_token issued? A cheap check run BEFORE the
    session lookup, so a junk Bearer value is refused without opening a database
    connection (OWASP Denial of Service cheat sheet: cheap checks first). Shape only --
    passing it proves nothing; the lookup still decides."""
    return bool(raw) and _TOKEN_SHAPE.fullmatch(raw) is not None


def _test() -> int:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    print("accounts")

    # ── the generic failure ──────────────────────────────────────────────────
    a, b = generic_failure(), generic_failure()
    check(a == b, "two calls return byte-identical refusals")
    check(a is not b, "...but NOT the same object -- mutating one must not affect the other")
    a["detail"] = "mutated"
    check(generic_failure()["detail"] != "mutated",
          "...proved: mutating a returned dict does not leak into the next call")

    # ── verify_login: timing-safe against an unknown email ──────────────────
    import gateway.passwords as passwords
    real_pw = "a correct horse battery staple"
    row = {"password_hash": passwords.hash_password(real_pw, n=1 << 12, r=8, p=1)}
    check(verify_login(row, real_pw), "the right password, against a real row, verifies")
    check(not verify_login(row, "wrong password entirely"),
          "a wrong password against a real row does not")
    check(not verify_login(None, real_pw),
          "an UNKNOWN email (no row) never verifies, whatever the password")
    check(not verify_login(None, "placedon-dummy-hash-no-account-has-this-password"),
          "...not even when the guess happens to equal the dummy string itself -- the "
          "`bool(row) and ...` guard, not the string's improbability, is what refuses it")
    check(not verify_login({"password_hash": None}, real_pw),
          "a row with NO password hash (invited, not yet accepted) does not verify either")

    # ── lockout ───────────────────────────────────────────────────────────────
    class _StubAuth:
        def __init__(self, failures: int, by_ip: int | None = None):
            self._failures = (failures, failures if by_ip is None else by_ip)

        def recent_failures(self, *, email_hash, ip_hash, since):
            return self._failures

    check(check_lockout(_StubAuth(0), email_hash="e", ip_hash="i") is None,
          "0 failures: not locked out")
    check(check_lockout(_StubAuth(LOGIN_LOCKOUT_MAX - 1), email_hash="e", ip_hash="i") is None,
          f"{LOGIN_LOCKOUT_MAX - 1} failures: still not locked out -- one under the line")
    out = check_lockout(_StubAuth(LOGIN_LOCKOUT_MAX), email_hash="e", ip_hash="i")
    check(out is not None and out["code"] == "LOCKED_OUT",
          f"{LOGIN_LOCKOUT_MAX} failures: LOCKED_OUT")
    check(out["retry_after"] == LOGIN_LOCKOUT_WINDOW_SECONDS,
          "...carrying retry_after")
    out2 = check_lockout(_StubAuth(LOGIN_LOCKOUT_MAX + 50), email_hash="e", ip_hash="i")
    check(out2 is not None and out2["code"] == "LOCKED_OUT",
          "...and MORE failures stays locked out rather than overflowing into something else")

    check(check_lockout(_StubAuth(0, LOGIN_LOCKOUT_IP_MAX - 1), email_hash="e", ip_hash="i")
          is None,
          f"{LOGIN_LOCKOUT_IP_MAX - 1} failures from one ADDRESS (an office NAT), none for this "
          "email: not locked out -- the address line is higher than the email line")
    check(LOGIN_LOCKOUT_IP_MAX > LOGIN_LOCKOUT_MAX,
          "...and that holds by construction: the per-address line is above the per-email one")
    by_ip = check_lockout(_StubAuth(0, LOGIN_LOCKOUT_IP_MAX), email_hash="e", ip_hash="i")
    check(by_ip is not None and by_ip == out,
          f"{LOGIN_LOCKOUT_IP_MAX} failures from one address: LOCKED_OUT, with a refusal "
          "identical to the per-email one (it does not say which line tripped)")
    check(check_lockout(_StubAuth(LOGIN_LOCKOUT_MAX, 0), email_hash="e", ip_hash="i") is not None,
          "an email at its line is locked even from a fresh address (rotating IPs buys nothing)")

    class _WindowAuth:
        """Proves the WINDOW, not just the count, is threaded through."""
        def __init__(self):
            self.seen_since = None

        def recent_failures(self, *, email_hash, ip_hash, since):
            self.seen_since = since
            return 0, 0

    probe = _WindowAuth()
    now = _dt.datetime(2026, 1, 1, tzinfo=_dt.timezone.utc)
    check_lockout(probe, email_hash="e", ip_hash="i", now=now)
    check(probe.seen_since == now - _dt.timedelta(seconds=LOGIN_LOCKOUT_WINDOW_SECONDS),
          "the window passed to recent_failures is exactly LOGIN_LOCKOUT_WINDOW_SECONDS "
          "before `now`, not a different constant living in two places")

    # ── token minting ─────────────────────────────────────────────────────────
    from gateway.auth import hash_key
    raw1, hash1 = mint_token()
    raw2, hash2 = mint_token()
    check(raw1 != raw2, "two mints are two different tokens")
    check(hash1 == hash_key(raw1) and hash2 == hash_key(raw2),
          "...and each hash is sha256 of its own raw token")
    check(len(raw1) >= 40, f"a minted token is long ({len(raw1)} chars of urlsafe base64)")
    check(len(hash1) == 64 and all(c in "0123456789abcdef" for c in hash1),
          "...stored as a 64-char lowercase hex sha256, matching 026's CHECK constraint")
    check(all(is_token_shaped(mint_token()[0]) for _ in range(200)),
          "every minted token passes the shape check (200 mints)")
    check(not any(is_token_shaped(junk) for junk in (
              None, "", "not-a-real-key", raw1[:-1], raw1 + "A", raw1[:-1] + "=",
              raw1[:-1] + "/", raw1[:-1] + "\n", "x" * 4096)),
          "junk, one char short or long, padding, non-urlsafe chars, a trailing newline and "
          "an oversized value are all refused by shape")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(_test())
