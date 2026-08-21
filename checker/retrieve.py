"""
The composed retrieval entry point: query in, evidence pack out.

The three layers below it are each correct alone. Composing them introduced a failure neither
could see, which is why this file exists rather than callers wiring them up ad hoc:

    "rule 4"  ->  legal_retrieval abstains (no Rules corpus exists)
              ->  text_search falls through and returns Act s.398, s.469
              ->  the pack marks them usable

The exact resolver's deliberate refusal to guess was undone by the keyword fallback. That is the
Act-versus-Rule collision this project has already been bitten by, reappearing at the seam.

The rule that fixes it: **a query that names a provision is answered by the resolver or not at
all.** Falling back to a text search there means answering a citation nobody asked us to
interpret. A query that names no provision may fall through, because there is no citation to
betray.

Run: python3 checker/retrieve.py
"""
from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from checker.evidence_pack import EvidencePack, build_pack
from checker.legal_retrieval import Hit, names_a_provision, resolve
from checker.text_search import search

__all__ = ["retrieve", "ROUTE_EXACT", "ROUTE_SEARCH", "ROUTE_ABSTAIN"]

ROUTE_EXACT = "exact"
ROUTE_SEARCH = "search"
ROUTE_ABSTAIN = "abstain"

SEARCH_TOP_K = 3


def _rows(hits: list[Hit]) -> list[dict]:
    return [{"section_number": h.ref.number, "section_id": h.section_id,
             "title": h.title, "defects": h.defects}
            for h in hits if h.section_id]


def retrieve(query: str, *, top_k: int = SEARCH_TOP_K) -> tuple[EvidencePack, str]:
    """Resolve a query to an evidence pack, and say which route produced it.

    Returns (pack, route). ROUTE_ABSTAIN means the query cited something we cannot resolve; the
    pack is empty and reports insufficient evidence rather than offering a near-miss.
    """
    hits = resolve(query)
    if hits:
        return build_pack(_rows(hits), query=query), ROUTE_EXACT

    if names_a_provision(query):
        # Cited, unresolvable. Do NOT search -- see the module docstring.
        return build_pack([], query=query), ROUTE_ABSTAIN

    rows = search(query, top_k=top_k)
    return build_pack(rows, query=query), (ROUTE_SEARCH if rows else ROUTE_ABSTAIN)


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"[PASS] {label}")
        else:
            fail += 1; print(f"[FAIL] {label}")

    pack, route = retrieve("s.173")
    check(route == ROUTE_EXACT, "an exact citation takes the exact route")
    check([p.key for p in pack.usable] == ["ACT:COMPANIES_ACT_2013:S173"],
          "s.173 is usable evidence")

    # The regression this module exists for.
    pack, route = retrieve("rule 4")
    check(route == ROUTE_ABSTAIN, "'rule 4' abstains rather than searching")
    check(not pack.to_dict()["provisions"], "'rule 4' returns NO provisions")
    check(pack.insufficient_evidence, "'rule 4' reports insufficient evidence")

    for q in ("r.56", "RULE:COMPANIES_MEETINGS_BOARD_POWERS_2014:R56", "rule 15"):
        p, r = retrieve(q)
        check(r == ROUTE_ABSTAIN and not p.to_dict()["provisions"],
              f"{q!r} never falls through to an Act section")

    # A citation we simply do not hold must not be softened into a search either.
    p, r = retrieve("s.9999")
    check(r == ROUTE_ABSTAIN, "an unknown section number abstains")
    p, r = retrieve("section 11")
    check(r == ROUTE_ABSTAIN, "a section omitted in the source abstains")

    # No citation named -> search is legitimate.
    pack, route = retrieve("related party transactions")
    check(route == ROUTE_SEARCH, "a concept query is allowed to search")
    check("ACT:COMPANIES_ACT_2013:S188" in [p.key for p in pack.usable],
          "concept query reaches s.188")

    pack, route = retrieve("what colour is the sky")
    check(route == ROUTE_ABSTAIN and pack.insufficient_evidence,
          "a nonsense query yields an empty, insufficient pack")

    # Defects survive the whole pipeline.
    pack, _ = retrieve("s.16")
    check(not pack.usable, "SD-002 pre-amendment text is not usable evidence")
    check(pack.to_dict()["provisions"], "...but it is still VISIBLE in the pack")
    check(pack.insufficient_evidence, "a pack of only-defective law is insufficient")

    block = retrieve("s.173")[0].prompt_block()
    check("INSUFFICIENT EVIDENCE" in block, "the prompt block names the abstention answer")
    check("bare section number is not an identity" in block.lower(),
          "the prompt block forbids bare-number citation")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
