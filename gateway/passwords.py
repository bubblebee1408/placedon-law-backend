#!/usr/bin/env python3
"""Password hashing with `hashlib.scrypt`. No new dependency, and no plaintext anywhere.

8a. scrypt is in the standard library, which matters here: CLAUDE.md requires a stated
reason for every new dependency, and "we need bcrypt to hash a password" is not one when
Python ships a memory-hard KDF that OWASP recommends.

## Why scrypt and not sha256

`gateway/auth.py` hashes API KEYS with a single SHA-256, and says why: a key is 256 random
bits from `secrets.token_urlsafe`, so there is nothing to guess and a slow KDF would only
slow the server. **A password is the opposite.** It is chosen by a person, it is short, and
it is reused. Hashing one with SHA-256 means an attacker with the table tries a billion
candidates a second.

So the two live in different files with different functions, rather than one `hash()`
someone later reuses for the wrong thing.

## The stored form

    scrypt$n$r$p$<salt b64>$<hash b64>

Parameters are stored WITH the hash, not read from this module at verification time. That
is what lets the cost be raised later without invalidating every existing password: an old
hash verifies against its own parameters, and `needs_rehash()` says it should be replaced
on next login.

Run: PYTHONPATH=. python3 gateway/passwords.py --test
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

__all__ = ["hash_password", "verify_password", "needs_rehash", "MIN_LENGTH",
            "PasswordError"]

# OWASP's scrypt floor (2024): N=2^17, r=8, p=1. Memory is 128*N*r = 128 MiB at this N,
# which is the point -- it is what makes a GPU farm expensive rather than cheap.
_N, _R, _P = 1 << 17, 8, 1
_SALT_BYTES = 16
_KEY_LEN = 32

# Short enough to be guessed is short enough to refuse. Not a complexity rule: length is
# the only password requirement with evidence behind it, and composition rules push people
# toward Passw0rd! which is worse.
MIN_LENGTH = 12


class PasswordError(ValueError):
    """A password that cannot be stored or a hash that cannot be read."""


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def hash_password(password: str, *, n: int = _N, r: int = _R, p: int = _P) -> str:
    """The stored form. A fresh salt every time, so two identical passwords differ."""
    if not isinstance(password, str):
        raise PasswordError(f"a password is a string, got {type(password).__name__}")
    if len(password) < MIN_LENGTH:
        raise PasswordError(
            f"a password must be at least {MIN_LENGTH} characters; this one is "
            f"{len(password)}. Length is the only requirement with evidence behind it")
    salt = secrets.token_bytes(_SALT_BYTES)
    key = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p,
                         dklen=_KEY_LEN, maxmem=132 * 1024 * 1024)
    return f"scrypt${n}${r}${p}${_b64(salt)}${_b64(key)}"


def _parse(stored: str):
    try:
        scheme, n, r, p, salt, key = str(stored).split("$")
        if scheme != "scrypt":
            raise ValueError(scheme)
        return int(n), int(r), int(p), base64.b64decode(salt), base64.b64decode(key)
    except Exception as e:                                       # noqa: BLE001
        raise PasswordError(f"not a stored scrypt hash: {type(e).__name__}") from None


def verify_password(password: str, stored: str) -> bool:
    """True when the password matches. Compared with `hmac.compare_digest`.

    Verified against the PARAMETERS IN THE HASH, not this module's current ones, so
    raising the cost later does not lock everybody out.
    """
    if not isinstance(password, str) or not stored:
        return False
    try:
        n, r, p, salt, expected = _parse(stored)
    except PasswordError:
        return False
    try:
        got = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p,
                             dklen=len(expected), maxmem=132 * 1024 * 1024)
    except ValueError:
        return False
    # Constant time. A `==` here leaks how many leading bytes matched, one request at a
    # time, which is enough to reconstruct the hash.
    return hmac.compare_digest(got, expected)


def needs_rehash(stored: str) -> bool:
    """Was this hashed with weaker parameters than we use now?"""
    try:
        n, r, p, _salt, _key = _parse(stored)
    except PasswordError:
        return True
    return (n, r, p) < (_N, _R, _P)


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

    print("passwords")
    # Cheap parameters for the gate. The SHIPPED ones are asserted separately below; a
    # suite that hashed at 128 MiB a dozen times would be a suite nobody runs.
    FAST = {"n": 1 << 12, "r": 8, "p": 1}
    PW = "correct horse battery staple"
    h = hash_password(PW, **FAST)

    check(h.startswith("scrypt$"), f"the stored form names its scheme ({h[:12]}...)")
    check(PW not in h, "the password itself is NOT in the stored form")
    check(verify_password(PW, h), "the right password verifies")
    check(not verify_password(PW + "x", h), "a wrong password does not")
    check(not verify_password("", h), "an empty password does not")
    check(not verify_password(PW, ""), "an empty hash verifies nothing")
    check(not verify_password(PW, "garbage"), "a malformed hash verifies nothing, and "
                                              "does not raise into the caller")
    check(hash_password(PW, **FAST) != h,
          "the SAME password hashes differently twice -- a fresh salt, so a stolen table "
          "does not show which users share a password")
    check(verify_password(PW, hash_password(PW, **FAST)),
          "...and both still verify")

    for short in ("", "short", "elevenchars"):
        try:
            hash_password(short, **FAST)
            check(False, f"a {len(short)}-character password is refused")
        except PasswordError:
            check(True, f"a {len(short)}-character password is REFUSED (minimum "
                        f"{MIN_LENGTH})")
    check(len("elevenchars") == MIN_LENGTH - 1,
          "...and the boundary case really is one short of the minimum")

    # Parameters travel with the hash, so the cost can rise later.
    weak = hash_password(PW, n=1 << 12, r=8, p=1)
    check(verify_password(PW, weak),
          "a hash made with WEAKER parameters still verifies -- against its own, not "
          "this module's")
    check(needs_rehash(weak),
          "...and is reported as needing a rehash, so it is replaced on next login")
    check(not needs_rehash(hash_password(PW)),
          "...while one at the current cost does not")
    check(needs_rehash("garbage"),
          "an unreadable hash needs a rehash: it cannot be trusted and must not be kept")

    # The shipped cost, asserted without paying it a dozen times.
    check((_N, _R, _P) == (1 << 17, 8, 1),
          f"the SHIPPED parameters are OWASP's scrypt floor, N=2^17 ({_N}, {_R}, {_P})")
    import inspect
    src = inspect.getsource(hash_password)
    check("secrets.token_bytes" in src,
          "the salt comes from `secrets`, not `random`")

    # The separation this file exists for.
    import ast
    import pathlib
    auth = pathlib.Path(__file__).resolve().parent / "auth.py"
    tree = ast.parse(auth.read_text(encoding="utf-8"))
    names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    check("scrypt" not in names,
          "gateway/auth.py does NOT use scrypt: an API key is 256 random bits and a slow "
          "KDF would only slow the server. Two different problems, two files")
    mods = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import)
            for a in n.names}
    check("passwords" not in mods,
          "...and it does not import this module, so nobody can reach for the wrong "
          "hash by autocomplete")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_test())
    print(__doc__)
