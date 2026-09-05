"""A licensed MCA21-aggregator adapter — the concrete L1 corporate-data provider.

`corporate_data.py` defined the seam (CorporateRecord, the LicensedAggregatorProvider
that refuses). This is the concrete provider against a CONTRACTED, MCA-sanctioned
aggregator (a Surepass / FileSure-class API), plus the mapper that turns its
response into a `CorporateRecord` for the entity graph.

## The two lines this module holds

1. **Licensed, never scraped.** There is no default MCA21 endpoint and no scraping
   path. `fetch()` refuses unless a `transport` is injected — either the real
   `http_transport` built from a contracted base URL + API key, or a test fake.
   The provider cannot be talked into hitting MCA21 directly.

2. **Facts with provenance, never conclusions.** A record is what the registry
   filing says (directors, controllers, holdings), tagged with its source and fetch
   time. It decides nothing; the deciders run on the graph exactly as for
   hand-entered data. Completeness (declare_complete_into) is asserted only when the
   response marks a set complete — so a NEGATIVE ("not a director") is earned.

## Normalised response schema (what the mapper expects)

Aggregators differ, so a thin per-aggregator `normalize` step maps their raw JSON to
this shape; the mapper below then validates it:

    {"cin": str, "company_class": "private"|"public"|"opc"|None,
     "directors": [{"din": str, "resident_days": int|None}], "directors_complete": bool,
     "controllers": [str(cin)], "controllers_complete": bool,
     "holdings": [{"holder_cin": str, "percent": float|None}], "holdings_complete": bool}
"""
from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Callable

from checker.corporate_data import (CorporateRecord, DirectorRef, HoldingRef,
                                    to_entity_graph)
from checker.entity_graph import EntityGraph

Transport = Callable[[str], dict]     # cin -> raw response dict


class NotConfigured(RuntimeError):
    """The provider has no licensed transport, so it will not fetch."""


class AggregatorResponseError(ValueError):
    """The aggregator response did not match the normalised schema."""


@dataclass(frozen=True)
class AggregatorConfig:
    """Where the contracted aggregator lives, and how to authenticate.

    base_url and api_key come from the environment / a secret manager, never the
    code. Absent either, the provider refuses to fetch.
    """
    base_url: str = ""
    api_key: str = ""
    provider_name: str = ""
    auth_header: str = "Authorization"     # or e.g. "x-api-key", per the contract
    path_template: str = "/company/{cin}"  # per the contract

    @classmethod
    def from_env(cls, prefix: str = "MCA_AGG") -> "AggregatorConfig":
        return cls(
            base_url=os.environ.get(f"{prefix}_BASE_URL", ""),
            api_key=os.environ.get(f"{prefix}_API_KEY", ""),
            provider_name=os.environ.get(f"{prefix}_NAME", ""),
            auth_header=os.environ.get(f"{prefix}_AUTH_HEADER", "Authorization"),
            path_template=os.environ.get(f"{prefix}_PATH", "/company/{cin}"))

    @property
    def ready(self) -> bool:
        return bool(self.base_url and self.api_key)


def record_from_normalised(data: dict, *, source: str,
                           fetched_at: date | None) -> CorporateRecord:
    """Map a normalised aggregator response to a CorporateRecord. Validates strictly."""
    if not isinstance(data, dict):
        raise AggregatorResponseError("response must be a JSON object")
    cin = data.get("cin")
    if not cin:
        raise AggregatorResponseError("response is missing 'cin'")

    def _directors() -> tuple[DirectorRef, ...]:
        out = []
        for d in data.get("directors", []) or []:
            din = (d or {}).get("din")
            if not din:
                raise AggregatorResponseError("a director entry is missing 'din'")
            out.append(DirectorRef(din, resident_days=d.get("resident_days")))
        return tuple(out)

    def _holdings() -> tuple[HoldingRef, ...]:
        out = []
        for h in data.get("holdings", []) or []:
            hc = (h or {}).get("holder_cin")
            if not hc:
                raise AggregatorResponseError("a holding entry is missing 'holder_cin'")
            pct = h.get("percent")
            if pct is not None and not (0.0 <= float(pct) <= 100.0):
                raise AggregatorResponseError(f"holding percent out of range: {pct}")
            out.append(HoldingRef(hc, percent=(float(pct) if pct is not None else None)))
        return tuple(out)

    controllers = tuple(data.get("controllers", []) or [])
    if any(not c for c in controllers):
        raise AggregatorResponseError("a controller CIN is empty")

    return CorporateRecord(
        cin=cin,
        company_class=data.get("company_class"),
        directors=_directors(),
        directors_complete=bool(data.get("directors_complete", False)),
        controllers=controllers,
        controllers_complete=bool(data.get("controllers_complete", False)),
        holdings=_holdings(),
        holdings_complete=bool(data.get("holdings_complete", False)),
        source=source,
        fetched_at=fetched_at)


def http_transport(config: AggregatorConfig, *, timeout: float = 20.0) -> Transport:
    """Build the real transport against a CONTRACTED aggregator. Refuses if unconfigured.

    This is the ONLY code that talks to the network, and it talks to the licensed
    aggregator's API (with an API key), never to MCA21 directly and never a scraper.
    It is kept behind config so nothing else learns an endpoint. Returns the raw
    response dict; a per-aggregator `normalize` maps it to the schema above.
    """
    if not config.ready:
        raise NotConfigured(
            "no contracted aggregator configured: set MCA_AGG_BASE_URL and "
            "MCA_AGG_API_KEY (from your signed licence). Do not scrape MCA21.")

    def _fetch(cin: str) -> dict:
        url = config.base_url.rstrip("/") + config.path_template.format(cin=cin)
        req = urllib.request.Request(url, headers={
            config.auth_header: config.api_key,
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=timeout) as r:   # noqa: S310 (licensed API)
            return json.loads(r.read().decode("utf-8"))

    return _fetch


class MCAAggregatorProvider:
    """Fetch a CorporateRecord from a licensed aggregator. Testable via `transport`."""

    def __init__(self, config: AggregatorConfig | None = None, *,
                 transport: Transport | None = None,
                 normalize: Callable[[dict], dict] | None = None):
        self.config = config or AggregatorConfig()
        self._transport = transport
        self._normalize = normalize or (lambda d: d)

    def _get_transport(self) -> Transport:
        if self._transport is not None:
            return self._transport
        # No injected transport: build the real one, which itself refuses if the
        # licence is not configured. There is no scraping fallback.
        return http_transport(self.config)

    def fetch(self, cin: str) -> CorporateRecord:
        raw = self._get_transport()(cin)
        data = self._normalize(raw)
        source = ("MCA21 via " + (self.config.provider_name or "licensed aggregator"))
        fetched = datetime.now(timezone.utc).date()
        return record_from_normalised(data, source=source, fetched_at=fetched)

    def graph_for(self, cin: str, graph: EntityGraph | None = None) -> EntityGraph:
        """Fetch and map straight into the entity graph."""
        return to_entity_graph(self.fetch(cin), graph)


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

    print("mca_aggregator")
    from checker.entity_graph import Answer, Rel

    # A fixture response, as a licensed aggregator would return (normalised).
    fixture = {
        "cin": "U74999KA2019PTC000042", "company_class": "private",
        "directors": [{"din": "DIN0001", "resident_days": 200}, {"din": "DIN0002"}],
        "directors_complete": True,
        "controllers": ["U00000KA2010PLC000009"], "controllers_complete": True,
        "holdings": [{"holder_cin": "U00000KA2010PLC000009", "percent": 60.0}],
        "holdings_complete": True,
    }

    # ── the mapper produces a provenanced record ────────────────────────────
    rec = record_from_normalised(fixture, source="MCA21 via TestAgg",
                                 fetched_at=date(2026, 9, 5))
    check(rec.cin == "U74999KA2019PTC000042", "the CIN maps through")
    check([d.din for d in rec.directors] == ["DIN0001", "DIN0002"],
          "directors map to DIN refs")
    check(rec.directors_complete and rec.source == "MCA21 via TestAgg",
          "completeness and provenance are carried")

    # ── the provider (fake transport) fetches and maps into the graph ───────
    prov = MCAAggregatorProvider(transport=lambda cin: fixture)
    g = prov.graph_for("U74999KA2019PTC000042")
    check(g.is_director("DIN0001", "U74999KA2019PTC000042") is Answer.YES,
          "a fetched directorship lands in the graph")
    check(g.is_director("DIN9999", "U74999KA2019PTC000042") is Answer.NO,
          "with the board marked complete, a non-director reads NO")
    check(g.shareholding("U00000KA2010PLC000009", "U74999KA2019PTC000042") == 60.0,
          "shareholding maps through")
    check(all(r.basis.startswith("MCA21 via") for r in g.relationships),
          "every graph edge is traceable to the aggregator source")

    # ── a per-aggregator normalize step is applied ──────────────────────────
    raw_vendor = {"CompanyId": "U1", "Directors": [{"DIN": "DINX"}]}
    def _normalize(raw):
        return {"cin": raw["CompanyId"],
                "directors": [{"din": d["DIN"]} for d in raw.get("Directors", [])],
                "directors_complete": False}
    prov2 = MCAAggregatorProvider(transport=lambda c: raw_vendor, normalize=_normalize)
    rec2 = prov2.fetch("U1")
    check(rec2.cin == "U1" and rec2.directors[0].din == "DINX",
          "a vendor-specific normalize maps raw JSON to the schema")

    # ── malformed responses are rejected, not mapped ────────────────────────
    for bad, why in (({"directors": [{"din": "D"}]}, "missing cin"),
                     ({"cin": "U1", "directors": [{}]}, "director missing din"),
                     ({"cin": "U1", "holdings": [{"holder_cin": "H", "percent": 250}]},
                      "percent out of range")):
        try:
            record_from_normalised(bad, source="s", fetched_at=None)
            check(False, f"a bad response is rejected ({why})")
        except AggregatorResponseError:
            check(True, f"a bad response is rejected ({why})")

    # ── the provider REFUSES without a licence (no scraping fallback) ───────
    unconfigured = MCAAggregatorProvider(AggregatorConfig())  # no transport, no creds
    try:
        unconfigured.fetch("U1")
        check(False, "an unconfigured provider refuses to fetch")
    except NotConfigured as e:
        check("scrape" in str(e).lower() and "licence" in str(e).lower(),
              "an unconfigured provider refuses, pointing at the licence not a scraper")

    check(not AggregatorConfig().ready and AggregatorConfig(base_url="u", api_key="k").ready,
          "config.ready requires both a base URL and an API key")

    # ── no scraping / MCA-direct import; only urllib (for the licensed API) ─
    import ast
    tree = ast.parse(open(__file__).read())
    roots = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            roots.update(a.name.split(".")[0] for a in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
            roots.add(n.module.split(".")[0])
    check(not (roots & {"playwright", "selenium", "bs4", "requests", "httpx"}),
          f"no scraping library is imported ({roots & {'playwright','bs4'} or 'clean'})")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
