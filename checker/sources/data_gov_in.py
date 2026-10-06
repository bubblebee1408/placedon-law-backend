#!/usr/bin/env python3
"""data.gov.in (OGD): a skeleton waiting for its key. OFFICIAL_LIVE — read today, not dated.

G1, move 17. The Open Government Data platform publishes government datasets through an API
keyed per user. `checker/sources/tiers.py` puts it at OFFICIAL_LIVE and says why that is not
HELD:

    OFFICIAL_LIVE  read off a government host minutes ago. Nobody ingested it, nothing
                   cross-rendered it, and a consolidation has no history -- so it can say
                   what the page says today and not what the law was on a date

So a row from here can SUPPORT an answer and can never make one VERIFIED. That is enforced
by `tiers.can_verify`, not by this file remembering.

## The same fail-closed shape as Indian Kanoon, for the same reason

No key means `KeyMissing`, which is an exception rather than an empty list. An empty list
would say "that dataset holds no such record" about a query that never ran, and an answer
built on that would be an abstention -- a VERIFIED product state -- resting on a fiction.

The transport is injected and this module imports no HTTP client, which is asserted by AST.

## One difference worth naming: the resource id is part of the request

OGD addresses a dataset by resource id, and a caller that guessed one would be reading a
different dataset from the one it believed. `fetch` takes the resource id and `search`
requires it, so there is no default dataset to be wrong about.

Run: PYTHONPATH=. python3 checker/sources/data_gov_in.py --test
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from checker.sources.connector_base import KeyedSource
from checker.sources.evidence import Evidence
from checker.sources.tiers import OFFICIAL_LIVE

SOURCE_ID = "data_gov_in"
ENV_VAR = "PLACEDON_DATA_GOV_IN_KEY"
BASE_URL = "https://api.data.gov.in"
RESOURCE_PATH = "/resource/{resource_id}"


class AsOfUnsupported(ValueError):
    """OGD serves what the dataset holds today. A past date is refused, not approximated."""


class NoResource(ValueError):
    """No resource id. There is deliberately no default dataset to be wrong about."""


class NoTransport(RuntimeError):
    """A key is configured and nobody injected a transport. Never built here."""


@dataclass(frozen=True)
class DataGovIn(KeyedSource):
    source_id: str = SOURCE_ID
    tier: str = OFFICIAL_LIVE
    env_var: str = ENV_VAR
    base_url: str = BASE_URL

    def search(self, query: str, *, as_of: str | None = None,
               resource_id: str = "") -> list:
        """Query one dataset. Raises KeyMissing with no key; never [] for that reason.

        `resource_id` is REQUIRED. OGD addresses a dataset by id, and a default would mean a
        caller could read a different dataset from the one it believed it was reading --
        which is worse than an error, because the rows would look fine.
        """
        key = self.require_key()
        if as_of:
            raise AsOfUnsupported(
                f"{SOURCE_ID} serves what the dataset holds TODAY and has no point-in-time "
                f"view. Asked about {as_of} it would answer about now, which is the "
                f"retracted mistake in docs/evidence/RETRACTIONS.md. Refused rather than "
                f"silently approximated")
        if not str(resource_id or "").strip():
            raise NoResource(
                f"{SOURCE_ID}: a resource_id is required. There is no default dataset on "
                f"purpose -- a default would let a caller read a different dataset from the "
                f"one it believed, and the rows would look fine")
        raw = self._get(RESOURCE_PATH.format(resource_id=resource_id),
                        {"filters[q]": query, "format": "json"}, key)
        body = json.loads(raw)
        return [self._evidence(rec, resource_id) for rec in (body.get("records") or [])]

    def fetch(self, ref: str) -> Evidence:
        """One dataset's metadata. `ref` IS the resource id."""
        key = self.require_key()
        if not str(ref or "").strip():
            raise NoResource(f"{SOURCE_ID}: fetch needs a resource id")
        raw = self._get(RESOURCE_PATH.format(resource_id=ref), {"format": "json"}, key)
        body = json.loads(raw)
        recs = body.get("records") or []
        return self._evidence(recs[0] if recs else body, str(ref))

    def _get(self, path: str, params: dict, key: str) -> bytes:
        if self.transport is None:
            raise NoTransport(
                f"{SOURCE_ID}: a key is configured and no transport was injected. This "
                f"connector never builds its own HTTP client -- one that did would be one "
                f"no test could stop from reaching the network")
        # The key goes in a HEADER, not in the query string, even though OGD's own examples
        # put it in `api-key=`. A credential in a url reaches every access log, proxy and
        # browser history between here and the host.
        return self.transport(self.base_url + path, params, {"api-key": key})

    def _evidence(self, rec: dict, resource_id: str) -> Evidence:
        from checker.sources import terms
        body = json.dumps(rec, sort_keys=True) if isinstance(rec, dict) else str(rec)
        return Evidence(
            tier=OFFICIAL_LIVE, source=SOURCE_ID,
            url=f"{self.base_url}/resource/{resource_id}",
            doc_id=str(rec.get("id") or resource_id) if isinstance(rec, dict)
            else str(resource_id),
            fetched_at=str(rec.get("fetched_at") or "") if isinstance(rec, dict) else "",
            sha256=hashlib.sha256(body.encode("utf-8")).hexdigest(),
            quoted_span=body,
            attribution=terms.attribution_for(SOURCE_ID))


def _test() -> int:
    import ast
    import inspect
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

    print("data_gov_in")

    from checker.sources.connector_base import KEY_MISSING, KeyMissing
    from checker.sources import terms
    from checker.sources.tiers import can_verify

    rec = terms.record_for(SOURCE_ID)
    check(rec.source_id == SOURCE_ID,
          f"a terms record exists for {SOURCE_ID} ({rec.source_id})")
    check(not can_verify(OFFICIAL_LIVE),
          "OFFICIAL_LIVE cannot VERIFY -- enforced by tiers.can_verify, not by this file "
          "remembering")

    saved = os.environ.pop(ENV_VAR, None)
    try:
        src = DataGovIn()
        for fn, label in ((lambda: src.search("company", resource_id="abc"), "search"),
                          (lambda: src.fetch("abc"), "fetch")):
            try:
                got = fn()
                check(False, f"{label} returned {got!r} with no key; it must raise")
            except KeyMissing as e:
                check(e.code == KEY_MISSING and e.env_var == ENV_VAR,
                      f"{label} raises KEY_MISSING naming {ENV_VAR} ({e.code})")
        check("NOT an empty result" in str(KeyMissing(SOURCE_ID, ENV_VAR)),
              "...and insists it is not an empty result: an empty one would claim the "
              "dataset holds no such record, about a query that never ran")

        os.environ[ENV_VAR] = "fixture-key"
        FIXTURE = json.dumps({"records": [
            {"id": "r1", "name": "ACME PRIVATE LIMITED", "state": "MH",
             "fetched_at": "2026-10-05T00:00:00Z"},
            {"id": "r2", "name": "BETA PRIVATE LIMITED", "state": "KA",
             "fetched_at": "2026-10-05T00:00:00Z"}]}).encode()
        seen: list = []

        def fixture_transport(url, params, headers):
            seen.append((url, dict(params), dict(headers)))
            return FIXTURE

        keyed = DataGovIn(transport=fixture_transport)
        rows = keyed.search("ACME", resource_id="9ef84268-d588-465a-a308-a864a43d0070")
        check(len(rows) == 2 and all(isinstance(r, Evidence) for r in rows),
              f"a fixture response parses into Evidence ({len(rows)})")
        check(all(r.tier == OFFICIAL_LIVE for r in rows), "...every row at OFFICIAL_LIVE")
        check(all(len(r.sha256) == 64 and r.quoted_span for r in rows),
              "...hash-stamped and quoted, which evidence.Evidence refuses to do without")
        # Whatever the TERMS RECORD says, and nothing invented. data.gov.in's ATTRIBUTION
        # clause is OPEN -- not read -- so `attribution_for` returns "" and so does this.
        # My first check asserted a non-empty attribution, which would have been an
        # invented one: OFFICIAL_LIVE is not in `ATTRIBUTION_REQUIRED`, and writing a
        # plausible credit line for a clause nobody has read is exactly the thing this
        # repository refuses. The day someone reads that clause, this starts carrying it.
        from checker.sources.tiers import ATTRIBUTION_REQUIRED
        check(all(r.attribution == terms.attribution_for(SOURCE_ID) for r in rows),
              f"...with attribution exactly as the terms record states it, which is "
              f"currently EMPTY because the clause is OPEN -- unread "
              f"({terms.attribution_for(SOURCE_ID)!r})")
        check(OFFICIAL_LIVE not in ATTRIBUTION_REQUIRED,
              f"...and OFFICIAL_LIVE does not require one, so an empty value is legitimate "
              f"rather than a validation hole ({ATTRIBUTION_REQUIRED})")
        check(terms.record_for(SOURCE_ID).clause("ATTRIBUTION").state == "OPEN",
              "...and the clause really is recorded as OPEN: an unread term is OPEN, never "
              "assumed permissive")
        check("9ef84268" in rows[0].url,
          f"...pointing at the resource it came from ({rows[0].url})")

        check(seen and "api-key" in seen[0][2] and "api-key" not in seen[0][0],
              f"the key goes in a HEADER, not the query string -- even though OGD's own "
              f"examples put it in `api-key=`, a credential in a url reaches every access "
              f"log and proxy on the way ({sorted(seen[0][2])})")
        check("fixture-key" not in seen[0][0] and "fixture-key" not in str(seen[0][1]),
              "...and appears in neither the url nor the params")

        # resource_id is required, with no default to be wrong about.
        try:
            keyed.search("x")
            check(False, "search with no resource_id must raise")
        except NoResource as e:
            check("no default dataset" in str(e),
                  "a query with no resource_id is refused: a default would let a caller "
                  "read a different dataset from the one it believed, and the rows would "
                  "look fine")
        try:
            keyed.search("x", resource_id="abc", as_of="2019-01-01")
            check(False, "as_of must be refused")
        except AsOfUnsupported as e:
            check("retracted mistake" in str(e),
                  "an as_of question is REFUSED rather than answered with today's dataset")
        try:
            DataGovIn().search("x", resource_id="abc")
            check(False, "a key with no transport must raise")
        except NoTransport:
            check(True, "with a key and no transport it raises rather than building a client")
    finally:
        if saved is None:
            os.environ.pop(ENV_VAR, None)
        else:
            os.environ[ENV_VAR] = saved

    mod = __import__("checker.sources.data_gov_in", fromlist=["x"])
    tree = ast.parse(inspect.getsource(mod))
    mods = {a.name.split(".")[0] for n in ast.walk(tree)
            if isinstance(n, ast.Import) for a in n.names}
    mods |= {(n.module or "").split(".")[0] for n in ast.walk(tree)
             if isinstance(n, ast.ImportFrom)}
    check(not ({"urllib", "requests", "httpx", "socket", "http"} & mods),
          f"this module imports NO http client: the transport is injected, which makes 'no "
          f"network call in any test' a property of the code rather than a promise "
          f"({sorted(mods)})")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    raise SystemExit(_test() if "--test" in sys.argv or len(sys.argv) == 1 else 0)
