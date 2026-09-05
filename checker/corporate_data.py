"""The seam where live corporate data enters — L1 of the Bloomberg-for-India design.

docs/BLOOMBERG_FOR_INDIA_ANALYSIS.md §4 puts everything on the entity graph. The
one genuinely-new engineering piece is feeding that graph from LIVE corporate data
(CIN, DIN, directors, cross-holdings, charges) instead of hand entry. This module
is that seam: a typed record, a provider contract, and a deterministic mapping into
`entity_graph`.

## The line this module holds: licensed access, never scraping

The pasted blueprint proposed scraping MCA21. `CLAUDE.md` forbids it, and this
project's whole value is that it does not bypass access controls. So the actual
fetch is an explicit integration point that REQUIRES a contracted, MCA-sanctioned
aggregator (the blueprint itself named Surepass / FileSure and peers). The provided
`LicensedAggregatorProvider` refuses to run until such a provider is wired, and
there is deliberately no scraping path anywhere in this file. A `CorporateRecord`
carries its source and fetch time so every graph edge derived from it is traceable.

## No unverified claims cross the boundary

A record is *facts from the registry*, not conclusions. Mapping it into the graph
adds relationship edges with a `basis` naming the source; it decides nothing. The
deciders (s.185/186/188) run on the graph exactly as they do for hand-entered data.
Because a registry filing is authoritative for "these are the company's directors",
the mapping asserts INcoming completeness (declare_complete_into) for the director
and shareholding sets it returns — but ONLY when the record marks them complete.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from datetime import date
from typing import Protocol

from checker.entity_graph import Entity, EntityGraph, Kind, Rel, Relationship


@dataclass(frozen=True)
class DirectorRef:
    din: str                       # Director Identification Number — the identity
    resident_days: int | None = None   # days in India this FY, if the source gives it


@dataclass(frozen=True)
class HoldingRef:
    holder_cin: str                # the body corporate that holds shares
    percent: float | None = None   # None = the source did not state it (never 0)


@dataclass(frozen=True)
class CorporateRecord:
    """Facts about one company, from an authorised registry source."""
    cin: str
    company_class: str | None = None            # private / public / opc, if given
    directors: tuple[DirectorRef, ...] = ()
    directors_complete: bool = False            # did the source return the FULL board?
    controllers: tuple[str, ...] = ()           # CINs of holding companies
    controllers_complete: bool = False
    holdings: tuple[HoldingRef, ...] = ()       # who holds shares in THIS company
    holdings_complete: bool = False
    # provenance — every edge derived from this record is traceable to it
    source: str = ""                            # e.g. "MCA21 via <licensed aggregator>"
    fetched_at: date | None = None

    def __post_init__(self) -> None:
        if not self.cin:
            raise ValueError("a corporate record needs a CIN")
        if not self.source:
            raise ValueError("a corporate record must name its source (provenance)")


class CorporateDataProvider(Protocol):
    """The contract a corporate-data source must satisfy."""
    def fetch(self, cin: str) -> CorporateRecord: ...


class LicensedAggregatorProvider:
    """A provider backed by a CONTRACTED MCA21 aggregator. Not yet wired.

    Instantiating and calling it raises with a clear message, on purpose: live
    corporate data requires a commercial agreement with an MCA-sanctioned
    aggregator, not a scraper. Wiring the actual API call is a governance/
    contractual step, and it belongs behind this method so nothing else in the
    codebase learns to talk to MCA21 directly.
    """

    def __init__(self, provider_name: str = ""):
        self.provider_name = provider_name

    def fetch(self, cin: str) -> CorporateRecord:
        raise NotImplementedError(
            "live corporate data requires a contracted, MCA-sanctioned aggregator "
            "(e.g. an authorised MCA21 API provider). Do not scrape MCA21 — see "
            "CLAUDE.md and docs/BLOOMBERG_FOR_INDIA_ANALYSIS.md §3.1. Wire the "
            "licensed provider's SDK here once an agreement is in place.")


def to_entity_graph(record: CorporateRecord,
                    graph: EntityGraph | None = None) -> EntityGraph:
    """Map a registry record into the entity graph. Deterministic; decides nothing.

    Adds the company, its directors (DIRECTOR_OF), its holding companies (CONTROLS),
    and its shareholders (HOLDS_SHARES_IN), each edge carrying the record's source
    as its basis. Where the record marks a set complete, the corresponding INcoming
    completeness is asserted so the deciders can return an earned NEGATIVE (e.g.
    "this counterparty is NOT a director") rather than UNKNOWN.
    """
    g = graph or EntityGraph()
    g = g.with_entity(Entity(record.cin, Kind.COMPANY))
    basis = record.source

    for d in record.directors:
        g = g.with_entity(Entity(d.din, Kind.INDIVIDUAL))
        g = g.with_relationship(
            Relationship(d.din, Rel.DIRECTOR_OF, record.cin,
                         as_of=record.fetched_at, basis=basis))
    if record.directors_complete:
        g = g.declare_complete_into(record.cin, Rel.DIRECTOR_OF)

    for holder_cin in record.controllers:
        g = g.with_entity(Entity(holder_cin, Kind.COMPANY))
        g = g.with_relationship(
            Relationship(holder_cin, Rel.CONTROLS, record.cin,
                         as_of=record.fetched_at, basis=basis))
    if record.controllers_complete:
        g = g.declare_complete_into(record.cin, Rel.CONTROLS)

    for h in record.holdings:
        g = g.with_entity(Entity(h.holder_cin, Kind.COMPANY))
        g = g.with_relationship(
            Relationship(h.holder_cin, Rel.HOLDS_SHARES_IN, record.cin,
                         as_of=record.fetched_at, percent=h.percent, basis=basis))
    if record.holdings_complete:
        g = g.declare_complete_into(record.cin, Rel.HOLDS_SHARES_IN)

    return g


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

    print("corporate_data")
    from checker.entity_graph import Answer, Rel as R

    # ── provenance is mandatory ─────────────────────────────────────────────
    try:
        CorporateRecord(cin="U1", source="")
        check(False, "a record without a source is rejected")
    except ValueError:
        check(True, "a record must carry its source (no unprovenanced data)")
    try:
        CorporateRecord(cin="", source="x")
        check(False, "a record without a CIN is rejected")
    except ValueError:
        check(True, "a record must carry a CIN")

    # ── a synthetic record maps into the graph ──────────────────────────────
    rec = CorporateRecord(
        cin="U74999KA2019PTC000001",
        company_class="private",
        directors=(DirectorRef("DIN0001", resident_days=200),
                   DirectorRef("DIN0002")),
        directors_complete=True,
        controllers=("U00000KA2010PLC000009",),
        controllers_complete=True,
        holdings=(HoldingRef("U00000KA2010PLC000009", percent=60.0),),
        holdings_complete=True,
        source="MCA21 via <licensed aggregator>",
        fetched_at=date(2026, 9, 1))
    g = to_entity_graph(rec)

    check(set(g.directors_of("U74999KA2019PTC000001")) == {"DIN0001", "DIN0002"},
          "directors map onto DIRECTOR_OF edges keyed by DIN")
    check(g.is_director("DIN0001", "U74999KA2019PTC000001") is Answer.YES,
          "a mapped directorship reads YES")
    # completeness lets a negative be earned
    check(g.is_director("DIN9999", "U74999KA2019PTC000001") is Answer.NO,
          "with the board marked complete, a non-director reads NO, not UNKNOWN")
    check(g.controllers_of("U74999KA2019PTC000001") == ["U00000KA2010PLC000009"],
          "controllers map onto CONTROLS edges")
    check(g.shareholding("U00000KA2010PLC000009", "U74999KA2019PTC000001") == 60.0,
          "shareholding percent maps onto HOLDS_SHARES_IN")

    # ── every derived edge is traceable to the record's source ──────────────
    check(all(r.basis == rec.source for r in g.relationships),
          "every edge carries the record's source as its basis (provenance)")

    # ── an incomplete record does NOT assert completeness ───────────────────
    partial = CorporateRecord(cin="U2", directors=(DirectorRef("DIN0003"),),
                              directors_complete=False, source="s")
    gp = to_entity_graph(partial)
    check(gp.is_director("DIN9999", "U2") is Answer.UNKNOWN,
          "an incomplete board leaves a non-director UNKNOWN, not NO")

    # ── the seam refuses to run without a licensed provider; no scraper ─────
    prov = LicensedAggregatorProvider()
    try:
        prov.fetch("U1")
        check(False, "the unwired provider refuses")
    except NotImplementedError as e:
        check("scrape" in str(e).lower() and "licensed" in str(e).lower()
              or "aggregator" in str(e).lower(),
              "the provider refuses and points at the licensed path, not scraping")

    # No scraping/network dependency -- checked by parsing THIS module's imports
    # via AST (grepping the source would hit this very banned-list, a self-
    # reference false positive this project has been bitten by before).
    import ast
    tree = ast.parse(Path(__file__).read_text())
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    banned = {"requests", "httpx", "urllib", "playwright", "selenium",
              "bs4", "aiohttp", "socket"}
    check(not (roots & banned),
          f"no scraping/network library is imported ({roots & banned or 'clean'})")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
