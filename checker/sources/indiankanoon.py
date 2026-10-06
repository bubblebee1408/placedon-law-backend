#!/usr/bin/env python3
"""Indian Kanoon: a skeleton waiting for its key. LICENSED tier — it can never VERIFY.

G1, move 17. Indian Kanoon publishes Indian case law. A judgment found there is a judgment
we found and quoted; it is **not** law we have checked, and `checker/sources/tiers.py` puts
it at LICENSED for that reason:

    LICENSED  a judgment on Indian Kanoon. Found and quoted, never verified law

## What this file does and does not do tonight

It does not make a request. `PLACEDON_INDIANKANOON_KEY` is not set, so every read raises
`KeyMissing` — which is an exception and not an empty list, because an empty list would say
"there is no case law on this" about a search that never happened.

What it DOES do is fix the shape, so tomorrow's key is a configuration change and not a
design question: the tier, the terms record it is bound to, the attribution its own licence
requires, and the parse of a response that already exists as a fixture.

## Attribution is not optional, and the code enforces it

`terms.py` records Indian Kanoon's RAG-and-logo clause, and `ATTRIBUTION_REQUIRED` names
LICENSED as a tier whose Evidence must carry the terms' own words. So `_evidence` sets
`attribution` from the terms record rather than from a string written here — a hand-written
attribution is one that stops matching the licence the day the licence changes.

Run: PYTHONPATH=. python3 checker/sources/indiankanoon.py --test
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from checker.sources.connector_base import KeyedSource
from checker.sources.evidence import Evidence
from checker.sources.tiers import LICENSED

SOURCE_ID = "indiankanoon"
ENV_VAR = "PLACEDON_INDIANKANOON_KEY"
BASE_URL = "https://api.indiankanoon.org"

# The paths the terms record confirms robots.txt allows. Written here so a future caller
# cannot reach a path nobody checked.
SEARCH_PATH = "/search/"
DOC_PATH = "/doc/{doc_id}/"


@dataclass(frozen=True)
class IndianKanoon(KeyedSource):
    source_id: str = SOURCE_ID
    tier: str = LICENSED
    env_var: str = ENV_VAR
    base_url: str = BASE_URL

    def search(self, query: str, *, as_of: str | None = None) -> list:
        """Search judgments. Raises KeyMissing with no key; never returns [] for that.

        `as_of` is REFUSED rather than ignored. Indian Kanoon serves what it has today and
        has no point-in-time view, so accepting the argument and quietly answering about now
        is the retracted mistake in `docs/evidence/RETRACTIONS.md`: using a current text as
        ground truth for a historical date.
        """
        key = self.require_key()
        if as_of:
            raise AsOfUnsupported(
                f"{SOURCE_ID} has no point-in-time view: it serves what it holds today. "
                f"Asked about {as_of}, it would answer about now, and answering a "
                f"historical question with today's text is the retracted mistake in "
                f"docs/evidence/RETRACTIONS.md. Refused rather than silently approximated")
        raw = self._get(SEARCH_PATH, {"formInput": query}, key)
        return [self._evidence(d) for d in (json.loads(raw).get("docs") or [])]

    def fetch(self, ref: str) -> Evidence:
        key = self.require_key()
        raw = self._get(DOC_PATH.format(doc_id=str(ref)), {}, key)
        return self._evidence(json.loads(raw))

    def _get(self, path: str, params: dict, key: str) -> bytes:
        if self.transport is None:
            raise NoTransport(
                f"{SOURCE_ID}: a key is configured and no transport was injected. This "
                f"connector never builds its own HTTP client -- one that did would be one "
                f"no test could stop from reaching the network")
        return self.transport(self.base_url + path, params,
                              {"Authorization": f"Token {key}"})

    def _evidence(self, doc: dict) -> Evidence:
        """One judgment as Evidence. The attribution comes from the TERMS RECORD.

        Not from a string written here: a hand-written attribution stops matching the licence
        the day the licence changes, and `checker/sources/evidence.py` refuses a LICENSED row
        without one.
        """
        from checker.sources import terms
        body = str(doc.get("headline") or doc.get("doc") or "").strip()
        return Evidence(
            tier=LICENSED, source=SOURCE_ID,
            url=f"{self.base_url}/doc/{doc.get('tid')}/" if doc.get("tid") else "",
            doc_id=str(doc.get("tid") or ""),
            fetched_at=str(doc.get("fetched_at") or ""),
            sha256=hashlib.sha256(body.encode("utf-8")).hexdigest(),
            quoted_span=body,
            # `terms.attribution_for` already exists and reads the clause's own quoted
            # words. My first version wrote a second implementation of it in this file --
            # which is how two sources of one fact start, and the licence is the last fact
            # to keep two copies of.
            attribution=terms.attribution_for(SOURCE_ID))


class AsOfUnsupported(ValueError):
    """This source cannot answer about a past date, and says so rather than approximating."""


class NoTransport(RuntimeError):
    """A key is configured and nobody injected a transport. Never built here."""


def _test() -> int:
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

    print("indiankanoon")

    from checker.sources.connector_base import KEY_MISSING, KeyMissing
    from checker.sources import terms

    # ── the terms record it is bound to exists, and is the one it names ─────
    rec = terms.record_for(SOURCE_ID)
    check(rec.source_id == SOURCE_ID,
          f"a terms record exists for {SOURCE_ID} -- a connector with none is a connector "
          f"whose licence nobody read ({rec.source_id})")
    check(BASE_URL in rec.terms_url or rec.terms_url.startswith("https://"),
          f"...with a terms url ({rec.terms_url})")

    saved = os.environ.pop(ENV_VAR, None)
    try:
        src = IndianKanoon()
        check(src.tier == LICENSED,
              f"the tier is LICENSED, so nothing from here can ever make a claim VERIFIED "
              f"({src.tier})")

        # ── with NO key: raises, never an empty list ────────────────────────
        for fn, label in ((lambda: src.search("annual general meeting"), "search"),
                          (lambda: src.fetch("12345"), "fetch")):
            try:
                got = fn()
                check(False, f"{label} returned {got!r} with no key; it must raise")
            except KeyMissing as e:
                check(e.code == KEY_MISSING and e.env_var == ENV_VAR,
                      f"{label} raises KEY_MISSING naming {ENV_VAR} ({e.code})")
        check(not src.configured and not src.health()["configured"],
              "health() says it is not configured")

        # The distinction that matters: this is not "no results".
        try:
            src.search("a phrase that would match nothing")
        except KeyMissing as e:
            check("NOT an empty result" in str(e),
                  "...and the message insists it is not an empty result, because an "
                  "abstention built on one would be a verified product state")

        # ── with a key and a FIXTURE transport: parses, no network ──────────
        os.environ[ENV_VAR] = "fixture-key"
        FIXTURE = json.dumps({"docs": [
            {"tid": 123456, "headline": "The company shall hold an annual general meeting.",
             "fetched_at": "2026-10-05T00:00:00Z"},
            {"tid": 777, "headline": "Leave of absence was granted to the director.",
             "fetched_at": "2026-10-05T00:00:00Z"}]}).encode()
        seen: list = []

        def fixture_transport(url, params, headers):
            seen.append((url, dict(params), sorted(headers)))
            return FIXTURE

        keyed = IndianKanoon(transport=fixture_transport)
        rows = keyed.search("annual general meeting")
        check(len(rows) == 2 and all(isinstance(r, Evidence) for r in rows),
              f"a fixture response parses into Evidence ({len(rows)})")
        check(all(r.tier == LICENSED for r in rows),
              "...every row at LICENSED")
        check(all(len(r.sha256) == 64 for r in rows),
              "...hash-stamped, which `evidence.Evidence` refuses to do without")
        check(all(r.attribution for r in rows),
              f"...and carrying ATTRIBUTION, which the licence requires and "
              f"`evidence.Evidence` refuses a LICENSED row without "
              f"({rows[0].attribution[:50]}…)")
        check(rows[0].quoted_span.startswith("The company shall hold"),
              f"...quoting the source's own words ({rows[0].quoted_span[:40]}…)")
        check(rows[0].url.endswith("/doc/123456/") and rows[0].doc_id == "123456",
              f"...pointing at the judgment it came from ({rows[0].url})")

        check(seen and seen[0][0] == BASE_URL + SEARCH_PATH,
              f"the transport was asked for the allowed search path and nothing else "
              f"({seen[0][0]})")
        check(any("Authorization" in h for h in seen[0][2]),
              "...with the key in a header rather than in the url, where it would reach "
              "every access log on the way")
        check("fixture-key" not in str(seen[0][0]),
              "...and NOT in the url")

        # A key with no transport is an error, not a quiet network call.
        try:
            IndianKanoon().search("x")
            check(False, "a configured key with no transport must raise")
        except NoTransport as e:
            check("never builds its own HTTP client" in str(e),
                  "with a key and no transport it raises rather than building a client -- "
                  "one that did would be one no test could stop reaching the network")

        # as_of is refused, not ignored.
        try:
            keyed.search("x", as_of="2019-04-01")
            check(False, "as_of must be refused")
        except AsOfUnsupported as e:
            check("retracted mistake" in str(e),
                  "an as_of question is REFUSED: this source serves today's text, and "
                  "answering a historical question with it is the retracted mistake in "
                  "docs/evidence/RETRACTIONS.md")
    finally:
        if saved is None:
            os.environ.pop(ENV_VAR, None)
        else:
            os.environ[ENV_VAR] = saved

    # ── no test in this file can reach the network ──────────────────────────
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(__import__("checker.sources.indiankanoon",
                                                  fromlist=["x"])))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    mods = {a.name.split(".")[0] for n in ast.walk(tree)
            if isinstance(n, ast.Import) for a in n.names}
    mods |= {(n.module or "").split(".")[0] for n in ast.walk(tree)
             if isinstance(n, ast.ImportFrom)}
    check(not ({"urllib", "requests", "httpx", "socket", "http"} & mods),
          f"this module imports NO http client: the transport is injected, which is what "
          f"makes 'no network call in any test' a property of the code rather than a "
          f"promise ({sorted(mods)})")
    check("urlopen" not in names,
          "...and calls no urlopen")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    raise SystemExit(_test() if "--test" in sys.argv or len(sys.argv) == 1 else 0)
