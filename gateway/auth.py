"""API keys, stored hashed, resolving to (tenant, actor).

Three properties, and the third is the one that gets lost first.

**The raw key is never stored.** `mint()` is the only place a raw key exists, it is
returned once, and what is kept is its SHA-256. A store that is read -- a leaked backup, a
dump, an over-broad SELECT -- yields hashes, and a hash is not a credential.

**A fast hash, deliberately, and it is only safe because of how keys are made.** `mint()`
draws 32 bytes from `secrets.token_urlsafe`, so there is no dictionary to run and no
password to guess; iterating SHA-256 would buy nothing against 256 bits of entropy. That
reasoning is a dependency, not a preference: **the day a human is allowed to choose a key,
this must become argon2 or bcrypt**, and `mint()` is the only door that keeps it untrue
today -- it refuses a caller-supplied key for exactly this reason.

**A key identifies a TENANT and an ACTOR, both UUIDs**, because gateway/audit.py refuses
anything else: "an audit row that cannot be joined to a tenant is not an audit row". The
key_id prefix is public and safe to log; the key is not, and `Principal` deliberately has
no field holding it.

Run: PYTHONPATH=. python3 gateway/auth.py
"""
from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass

KEY_BYTES = 32
PREFIX_LEN = 8
_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                   r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


class AuthError(PermissionError):
    """Refused. Carries no detail a caller could use to enumerate keys."""


@dataclass(frozen=True)
class Principal:
    """Who a request is. Note what is NOT here: the key."""
    tenant_id: str
    actor: str
    key_id: str
    label: str = ""
    # 8a. The SAFE default: a principal created without a role can read and change
    # nothing. The dangerous default is the other one, and it is the one that gets chosen
    # when a field is added to a class that already has callers.
    role: str = "viewer"

    def __post_init__(self) -> None:
        from gateway.roles import ROLES
        if self.role not in ROLES:
            raise ValueError(
                f"role must be one of {ROLES}, got {self.role!r}. An unknown role is not "
                f"treated as the lowest one: it is a row nobody meant to write.")
        for name in ("tenant_id", "actor"):
            if not _UUID.match(getattr(self, name) or ""):
                raise ValueError(
                    f"{name} must be a UUID, got {getattr(self, name)!r}. "
                    f"gateway/audit.py refuses anything else, and a request that cannot "
                    f"be written to the audit chain must not be served.")


def hash_key(raw: str) -> str:
    """The stored form. One-way, and the only form that touches disk."""
    return hashlib.sha256((raw or "").encode("utf-8")).hexdigest()


def key_id(raw: str) -> str:
    """A short public handle for logs and support. Not a secret, not sufficient to auth."""
    return hash_key(raw)[:PREFIX_LEN]


class KeyStore:
    """Hash -> Principal. The raw keys are not here, and cannot be recovered from here."""

    def __init__(self) -> None:
        self._by_hash: dict[str, Principal] = {}

    def mint(self, *, tenant_id: str, actor: str, label: str = "",
             role: str = "viewer") -> tuple[str, Principal]:
        """Create a key. The raw value is returned ONCE and never stored.

        There is no `add_existing(key)`. A caller-supplied key could be low entropy, and
        the whole argument for hashing with SHA-256 rather than argon2 rests on the key
        being 256 random bits. Leaving that door shut is what keeps the docstring true.
        """
        raw = secrets.token_urlsafe(KEY_BYTES)
        p = Principal(tenant_id=tenant_id, actor=actor, key_id=key_id(raw), label=label,
                      role=role)
        self._by_hash[hash_key(raw)] = p
        return raw, p

    def resolve(self, raw: str | None) -> Principal:
        """The principal for a key, or AuthError. Lookup is by hash, so no compare leaks."""
        if not raw:
            raise AuthError("no API key presented")
        p = self._by_hash.get(hash_key(raw))
        if p is None:
            # Deliberately the same message as the branch above. A refusal that said
            # "unknown key" versus "no key" would let a caller learn which of the two it
            # had, which is the first step of enumerating them.
            raise AuthError("no API key presented")
        return p

    def revoke(self, raw: str) -> bool:
        return self._by_hash.pop(hash_key(raw), None) is not None

    def __len__(self) -> int:
        return len(self._by_hash)

    @property
    def hashes(self) -> tuple[str, ...]:
        return tuple(self._by_hash)


def bearer(header: str | None) -> str | None:
    """The key out of an Authorization header, or None. `Bearer <key>`, case-insensitive."""
    if not header:
        return None
    parts = header.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


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

    T = "11111111-2222-3333-4444-555555555555"
    A = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    ks = KeyStore()
    raw, p = ks.mint(tenant_id=T, actor=A, label="ci")

    # ── the raw key is not kept ─────────────────────────────────────────────
    check(len(ks) == 1 and ks.hashes[0] == hash_key(raw),
          "what is stored is the hash of the key")
    check(raw not in ks.hashes and all(raw not in h for h in ks.hashes),
          "...and the raw key appears nowhere in the store")
    import dataclasses
    fields = {f.name for f in dataclasses.fields(Principal)}
    check("key" not in fields and "raw" not in fields and "secret" not in fields,
          f"...nor on the Principal, which has no field for it ({sorted(fields)})")
    check(len(raw) >= 40, f"a minted key is long ({len(raw)} chars of urlsafe base64)")
    a, _ = ks.mint(tenant_id=T, actor=A)
    check(a != raw, "two mints are two different keys")

    # ── resolve ─────────────────────────────────────────────────────────────
    check(ks.resolve(raw) == p, "the right key resolves to its principal")
    check(ks.resolve(raw).key_id == key_id(raw) and len(p.key_id) == PREFIX_LEN,
          "...carrying a short public handle for logs")
    for bad in (None, "", "not-a-key", raw + "x", raw[:-1]):
        try:
            ks.resolve(bad)
            check(False, f"{str(bad)[:12]!r} is refused")
        except AuthError as e:
            check("no API key presented" in str(e),
                  f"...refused with the SAME message as a missing key ({str(bad)[:10]!r}) "
                  f"-- distinguishing them is how a caller starts enumerating keys")

    check(ks.revoke(raw) and not ks.revoke(raw), "revoke removes it once")
    try:
        ks.resolve(raw)
        check(False, "a revoked key is refused")
    except AuthError:
        check(True, "...and a revoked key no longer resolves")

    # ── a key must name a tenant AND an actor, both UUIDs ───────────────────
    for t, act, why in ((("tenant"), A, "a non-UUID tenant"),
                        (T, "actor", "a non-UUID actor"),
                        ("", A, "an empty tenant")):
        try:
            KeyStore().mint(tenant_id=t, actor=act)
            check(False, f"{why} is refused")
        except ValueError as e:
            check("audit" in str(e),
                  f"{why} is refused, and the reason names the audit chain -- a request "
                  f"that cannot be written to it must not be served")

    # ── there is no door for a caller-supplied key ──────────────────────────
    check(not hasattr(ks, "add_existing") and not hasattr(ks, "add_key"),
          "there is no way to register a key someone else chose: the argument for SHA-256 "
          "over argon2 rests on 256 random bits, and a chosen key would make it untrue")

    # ── the header parser ───────────────────────────────────────────────────
    check(bearer("Bearer abc") == "abc" and bearer("bearer abc") == "abc",
          "Bearer is case-insensitive")
    for h in (None, "", "abc", "Basic abc", "Bearer", "Bearer   "):
        check(bearer(h) is None, f"{h!r} yields no key rather than a wrong one")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
