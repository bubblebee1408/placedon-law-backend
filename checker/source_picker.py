"""The pickable sources, and whether each can be switched on — the one authority for @-sources.

A question may be answered from a chosen set of sources ("Central law only", "case law only").
This module says WHAT is pickable and WHETHER it can be switched on; it never searches and never
decides law. The verb layer resolves a caller's `sources` against this, searches only the ones it
returns, and reports per source whether it was searched, searched-empty, or not searched.

## Display tiers are not verification tiers

The picker groups sources into three names a person recognises — HELD, LICENSED, PUBLIC — over the
real tiers in `checker/tier_rules`. The grouping changes nothing about verification: only HELD can
make an answer VERIFIED (`tier_rules.can_verify`), and a PUBLIC or LICENSED source can only support.
This module does not import a verification decision; it only labels.

## Unavailable is a named state, never "not found"

A source we cannot switch on says why — KEY_MISSING (an API key env var is unset), NOT_ACQUIRED (its
terms were never read, and an unread term is OPEN, not permission), or BLOCKED (robots refuses us,
with the origin and HTTP code). `resolve()` returns an unavailable pick as NOT_SEARCHED with that
state; it is never silently dropped and never collapsed into "no result".
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from checker.sources import terms

# ── display tiers (a grouping over tier_rules, not a new verification tier) ──
HELD = "HELD"
LICENSED = "LICENSED"
PUBLIC = "PUBLIC"

# ── availability states ──────────────────────────────────────────────────────
AVAILABLE = "available"
KEY_MISSING = "KEY_MISSING"
NOT_ACQUIRED = "NOT_ACQUIRED"
BLOCKED = "BLOCKED"

# The two built-ins that are not external terms records. `held` is our corpus; `vault` is the
# tenant's own uploaded documents (the UI reaches it by a Files button, but it is a source).
HELD_ID = "held"
VAULT_ID = "vault"

# A source that needs an API key to fetch. Unset env var => KEY_MISSING, even when terms permit.
KEY_ENV: dict[str, str] = {
    "indiankanoon": "PLACEDON_INDIANKANOON_KEY",
    "data_gov_in": "PLACEDON_DATA_GOV_IN_KEY",
}

# Display tier for each external source id. Case law is LICENSED (may support, never verify);
# official/open-government publishers are PUBLIC. Anything not named here defaults to PUBLIC.
_LICENSED_IDS = frozenset({"indiankanoon", "aws_sc_judgments", "aws_hc_judgments"})


@dataclass(frozen=True)
class Source:
    """One pickable source. `status`/`reason` are computed live — the env/terms can change."""
    id: str
    label: str
    tier: str                        # HELD | LICENSED | PUBLIC (display)
    status: str                      # available | KEY_MISSING | NOT_ACQUIRED | BLOCKED
    reason: str
    terms: dict = field(default_factory=dict)

    @property
    def switchable(self) -> bool:
        return self.status == AVAILABLE

    def to_dict(self) -> dict:
        return {"id": self.id, "label": self.label, "tier": self.tier,
                "status": self.status, "reason": self.reason,
                "switchable": self.switchable, "terms": self.terms}


def _external_status(source_id: str) -> tuple[str, str]:
    """(state, reason) for an external terms-recorded source.

    Order matters: robots/terms gate first (BLOCKED / NOT_ACQUIRED), because a key cannot rescue a
    source we are not allowed to fetch; only then the key (KEY_MISSING). `may_fetch` already carries
    the exact reason — robots origin + HTTP, or 'terms unread', or which clause prohibits us.
    """
    ok, why = terms.may_fetch(source_id)
    if not ok:
        state = BLOCKED if why.startswith("robots") else NOT_ACQUIRED
        return state, why
    env = KEY_ENV.get(source_id)
    if env and not os.environ.get(env):
        return KEY_MISSING, f"{env} is not set; the source permits us but no API key is configured"
    return AVAILABLE, why


def _tier_of(source_id: str) -> str:
    return LICENSED if source_id in _LICENSED_IDS else PUBLIC


def source(source_id: str) -> Source:
    """One source's live card. Raises KeyError for an id that is neither built-in nor recorded."""
    if source_id == HELD_ID:
        return Source(HELD_ID, "Companies Act 2013 (held corpus)", HELD, AVAILABLE,
                      "held and hash-stamped; the only tier that can make an answer VERIFIED")
    if source_id == VAULT_ID:
        return Source(VAULT_ID, "Your documents (vault)", PUBLIC, AVAILABLE,
                      "the tenant's own uploaded documents, searched as support, never VERIFIED")
    rec = terms.record_for(source_id)          # raises terms.NoTermsRecord for an unknown id
    state, reason = _external_status(source_id)
    return Source(source_id, rec.name, _tier_of(source_id), state, reason,
                  terms={"url": rec.terms_url or None, "read": rec.date_read or None,
                         "clauses": {c.topic: c.state for c in rec.clauses}})


def all_ids() -> tuple[str, ...]:
    """Every pickable id: the two built-ins then the external records, in a stable order."""
    return (HELD_ID, VAULT_ID) + terms.SOURCE_IDS


def listing() -> list[dict]:
    """Every source as a card for `sources.list`. Unavailable ones are listed, not hidden."""
    return [source(sid).to_dict() for sid in all_ids()]


# Default when a caller picks nothing: the held statute plus the tenant's own vault. Never the
# external sources — those are an explicit choice, since they may spend a key or leave the corpus.
DEFAULT: tuple[str, ...] = (HELD_ID, VAULT_ID)


@dataclass(frozen=True)
class Resolved:
    searchable: tuple[str, ...]              # ids that may be searched now
    unavailable: tuple[dict, ...]            # picked but not switchable: {id, status, reason}

    def to_dict(self) -> dict:
        return {"searchable": list(self.searchable), "unavailable": list(self.unavailable)}


def resolve(picked) -> Resolved:
    """Split a caller's pick into what may be searched and what cannot (with its named state).

    `picked` is None/empty -> DEFAULT (held + vault). An id we do not know is itself NOT_SEARCHED
    with an explicit reason, rather than a silent drop or a 500. De-duplicated, order preserved.
    """
    ids = tuple(dict.fromkeys(picked or DEFAULT))
    searchable, unavailable = [], []
    for sid in ids:
        try:
            s = source(sid)
        except (KeyError, terms.NoTermsRecord):
            unavailable.append({"id": sid, "status": "UNKNOWN",
                                "reason": f"no source {sid!r}; see sources.list"})
            continue
        if s.switchable:
            searchable.append(sid)
        else:
            unavailable.append({"id": sid, "status": s.status, "reason": s.reason})
    return Resolved(tuple(searchable), tuple(unavailable))


def _test() -> None:
    passed = failed = 0

    def check(cond: bool, label: str) -> None:
        nonlocal passed, failed
        if cond:
            passed += 1
            print(f"  [PASS] {label}")
        else:
            failed += 1
            print(f"  [FAIL] {label}")

    print("source_picker")

    # ── built-ins are always switchable, and held is the only HELD tier ──────
    h = source(HELD_ID)
    check(h.tier == HELD and h.status == AVAILABLE and h.switchable,
          f"held is HELD and available ({h.tier}, {h.status})")
    check(source(VAULT_ID).switchable, "the vault is switchable")
    check([s for s in listing() if s["tier"] == HELD] == [h.to_dict()],
          "exactly one source is displayed as HELD — the held corpus")

    # ── a key-gated source is KEY_MISSING keyless, and says which key ────────
    saved = os.environ.pop("PLACEDON_INDIANKANOON_KEY", None)
    try:
        ik = source("indiankanoon")
        check(ik.tier == LICENSED, f"indiankanoon is LICENSED ({ik.tier})")
        check(ik.status == KEY_MISSING and "PLACEDON_INDIANKANOON_KEY" in ik.reason
              and not ik.switchable,
              f"indiankanoon with no key is KEY_MISSING, not switchable, and names the key "
              f"({ik.status})")
        # ...and KEY_MISSING is NOT the same as 'not found' or 'blocked'
        check(ik.status not in (BLOCKED, NOT_ACQUIRED),
              "KEY_MISSING is its own state, distinct from BLOCKED/NOT_ACQUIRED")
    finally:
        if saved is not None:
            os.environ["PLACEDON_INDIANKANOON_KEY"] = saved

    # ── a source whose terms were never read is NOT_ACQUIRED, with the reason ─
    acquired = [s for s in listing() if s["status"] == NOT_ACQUIRED or s["status"] == BLOCKED]
    check(all(s["reason"] for s in acquired),
          "every unavailable external source carries a non-empty reason")
    check(any(s["status"] in (NOT_ACQUIRED, BLOCKED) for s in listing()),
          "at least one external source is NOT_ACQUIRED/BLOCKED (terms unread or robots)")

    # ── every display tier is one of the three the picker names ──────────────
    check(all(s["tier"] in (HELD, LICENSED, PUBLIC) for s in listing()),
          "every source's display tier is HELD / LICENSED / PUBLIC")

    # ── resolve: default is held + vault; nothing external by default ────────
    r = resolve(None)
    check(r.searchable == DEFAULT and r.unavailable == (),
          f"no pick -> held + vault, nothing external ({r.searchable})")
    check(set(DEFAULT) == {HELD_ID, VAULT_ID}, "the default is exactly held + vault")

    # ── resolve: an unavailable pick is preserved as NOT_SEARCHED, not dropped ─
    saved = os.environ.pop("PLACEDON_INDIANKANOON_KEY", None)
    try:
        r2 = resolve(["indiankanoon"])
        check(r2.searchable == () and len(r2.unavailable) == 1
              and r2.unavailable[0]["id"] == "indiankanoon"
              and r2.unavailable[0]["status"] == KEY_MISSING,
              f"a KEY_MISSING pick is returned unavailable with its state, never searched "
              f"({r2.to_dict()})")
        # held-only vs case-law-only resolve to DIFFERENT searchable sets
        rh = resolve(["held"])
        check(rh.searchable == ("held",) and r2.searchable == (),
              "held-only and case-law-only resolve to different searchable sets")
    finally:
        if saved is not None:
            os.environ["PLACEDON_INDIANKANOON_KEY"] = saved

    # ── an unknown id is a named refusal, not a crash ────────────────────────
    r3 = resolve(["nope"])
    check(r3.searchable == () and r3.unavailable[0]["status"] == "UNKNOWN",
          "an unknown source id is UNKNOWN with a reason, never a 500")

    # ── de-dup, order preserved ──────────────────────────────────────────────
    r4 = resolve(["held", "held", "vault"])
    check(r4.searchable == ("held", "vault"), f"duplicates collapse, order kept ({r4.searchable})")

    print(f"{passed}/{passed + failed} passed")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
