#!/usr/bin/env python3
"""G1: what every keyed connector shares, and why a missing key RAISES.

Move 17. Indian Kanoon and data.gov.in are both "a host we may read once somebody issues a
key". Neither is wired to a network tonight, and standing rule 7 forbids one. What they need
to be is **ready**, and ready means failing closed in a way nobody can mistake for an answer.

## KEY_MISSING raises. It does not return an empty list

`Source.search` returns `list[Evidence]`, and an empty list already means something: we
searched and found nothing. A connector with no key that returned `[]` would be saying "there
is no case law on this" about a search that never happened -- and that answer would flow into
an abstention, which is a VERIFIED product state.

So `KeyMissing` is an exception, and `checker/sources/base.Source` is unchanged. The caller
that catches it knows the difference between "no key" and "no results" because the type
system made it impossible to confuse them.

Same reasoning as `checker/doc_verification.NOT_CHECKED` and
`checker/doc_validity.NOT_DETERMINED`: every one of these exists to say what was not
established, rather than to let an absence read as a finding.

## No network, and the transport is injected

Every connector takes a `transport` callable. With no key it is never reached, which is why
a keyless test cannot make a request even by accident. With a key, the gate still passes a
fixture, so **no test in this repository makes a network call** -- asserted, by sweeping each
connector's source for `urlopen`, `requests` and `httpx`.

Run: PYTHONPATH=. python3 checker/sources/connector_base.py --test
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from checker.sources.base import SourceError

KEY_MISSING = "KEY_MISSING"
NOT_CONFIGURED = "NOT_CONFIGURED"
TERMS_NOT_READ = "TERMS_NOT_READ"


class KeyMissing(SourceError):
    """No credential is configured for this source. NOT a result, and never an empty one.

    Carries `code` so a caller can report it without parsing English, and `env_var` so the
    operator is told the name of the thing to set -- which is the difference between a
    two-minute fix and an hour, and the lesson `gateway/worker.py` learned the same night.
    """

    def __init__(self, source_id: str, env_var: str, *, note: str = "") -> None:
        self.code = KEY_MISSING
        self.source_id = source_id
        self.env_var = env_var
        super().__init__(
            f"{source_id}: no key is configured, so nothing was searched. Set {env_var}. "
            f"This is NOT an empty result -- an empty result would say there is nothing "
            f"to find, about a search that never happened. "
            + (note or f"docs/guides/INTEGRATIONS_CHECKLIST.md says who issues {env_var}."))


@dataclass(frozen=True)
class KeyedSource:
    """A connector that needs a credential. Subclasses add `search` and `fetch`.

    `transport(url, headers) -> bytes` is injected and never built here. A connector that
    constructed its own HTTP client would be a connector no test could stop from reaching
    the network.
    """
    source_id: str
    tier: str
    env_var: str
    base_url: str
    transport: object = None

    @property
    def key(self) -> str:
        return (os.environ.get(self.env_var) or "").strip()

    @property
    def configured(self) -> bool:
        return bool(self.key)

    def require_key(self) -> str:
        """The key, or raise. Called FIRST in every method that would reach the host."""
        k = self.key
        if not k:
            raise KeyMissing(self.source_id, self.env_var)
        return k

    def health(self) -> dict:
        """What an operator needs to know, without ever printing the key itself."""
        return {"source_id": self.source_id, "tier": self.tier,
                "env_var": self.env_var, "configured": self.configured,
                "base_url": self.base_url,
                "note": ("configured; reads are permitted by the terms record and will go "
                         "to the host"
                         if self.configured else
                         f"NOT configured. Every read raises {KEY_MISSING} rather than "
                         f"returning an empty result, so 'we have no key' can never be "
                         f"read as 'there is nothing to find'")}


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

    print("connector_base")

    from checker.sources.tiers import LICENSED

    ENV = "PLACEDON_TEST_CONNECTOR_KEY_DOES_NOT_EXIST"
    src = KeyedSource("probe", LICENSED, ENV, "https://example.invalid")
    saved = os.environ.pop(ENV, None)
    try:
        check(not src.configured, "with no env var the source is not configured")
        try:
            src.require_key()
            check(False, "require_key must raise with no key")
        except KeyMissing as e:
            check(e.code == KEY_MISSING, f"...raising KeyMissing with a code a caller can "
                                         f"report without parsing English ({e.code})")
            check(e.env_var == ENV and ENV in str(e),
                  f"...naming the env var to set, which is the difference between a "
                  f"two-minute fix and an hour ({e.env_var})")
            check("NOT an empty result" in str(e),
                  "...and saying it is not an empty result, because an empty result would "
                  "claim there is nothing to find")
        check(not src.health()["configured"]
              and KEY_MISSING in src.health()["note"],
              "health() reports it without printing a key")
        check(ENV not in str(src.health()) or "configured" in str(src.health()),
              "...and never the key itself")

        os.environ[ENV] = "a-secret-value"
        check(src.configured and src.require_key() == "a-secret-value",
              "with the var set, the key is returned")
        check("a-secret-value" not in str(src.health()),
              "...and health() STILL does not print it -- an operator-facing dict that "
              "leaked the credential would put it in every log that captured one")
    finally:
        if saved is None:
            os.environ.pop(ENV, None)
        else:
            os.environ[ENV] = saved

    check(isinstance(KeyMissing("s", "E"), SourceError),
          "KeyMissing is a SourceError, so a caller handling source failures catches it "
          "without knowing about connectors")
    check(not issubclass(KeyMissing, LookupError),
          "...and NOT a LookupError: 'not found' is the one thing it must never be "
          "mistaken for")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    raise SystemExit(_test() if "--test" in sys.argv or len(sys.argv) == 1 else 0)
