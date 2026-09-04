"""Structural retrieval — resolve a query to the statute chunks it admits.

T3 in docs/NEXT_MOVE_PLAN_2026_09_04.md. `retrieve.retrieve()` already resolves a
query to an evidence pack under the project's hardest-won discipline:

  * a query that names a provision is answered by the resolver or NOT AT ALL
    (no keyword fallback that betrays a citation),
  * only what a reviewer has ADMITTED for the mode is served,
  * withheld material is reported as withheld, never silently dropped.

This layer does not re-implement any of that. It calls `retrieve()`, takes the
provisions that survived its gating, and returns their STRUCTURAL chunks (from
structural_index) — so a caller gets "s.2(85)(i), the capital limb, verbatim,
with its hash" instead of a whole-section blob. Because it derives entirely from
`retrieve()`'s output, it cannot answer a citation `retrieve()` would abstain on,
and it cannot surface a section `retrieve()` withheld.

It is the bridge from retrieval to the E-gate (T4): the chunks it returns are the
candidate witness spans a model proposal must be entailed by.
"""
from __future__ import annotations

import re

from checker.retrieve import (MODE_MODEL, ROUTE_ABSTAIN, retrieve)
from checker.structural_chunk import Chunk
from checker.structural_index import chunks_for_section

# A provision key is "ACT:COMPANIES_ACT_2013:S173"; the section number is the tail.
_KEY_SECTION = re.compile(r":S(\d+[A-Z]?)$")


def _section_of_key(key: str) -> str | None:
    m = _KEY_SECTION.search(key)
    return m.group(1) if m else None


def structural_retrieve(query: str, *, mode: str = MODE_MODEL
                        ) -> tuple[list[Chunk], str, list[str]]:
    """(chunks, route, withheld) for a query.

    `route` is retrieve()'s own route (exact / search / abstain). On ROUTE_ABSTAIN
    the chunk list is empty — the query cited something unresolvable or wholly
    inadmissible, and offering a near-miss chunk would be the citation-betrayal
    the retrieval layer refuses. `withheld` carries retrieve()'s withheld notices
    unchanged, so "found but not admitted" stays distinct from "not found".
    """
    pack, route = retrieve(query, mode=mode)
    withheld = list(getattr(pack, "withheld_notices", ()) or ())
    if route == ROUTE_ABSTAIN:
        return [], route, withheld

    chunks: list[Chunk] = []
    seen: set[str] = set()
    for prov in pack.usable:
        sec = _section_of_key(getattr(prov, "key", ""))
        if not sec:
            continue
        for c in chunks_for_section(sec):
            if c.path not in seen:
                seen.add(c.path)
                chunks.append(c)
    return chunks, route, withheld


def chunks_for_query(query: str, *, mode: str = MODE_MODEL) -> list[Chunk]:
    """Just the chunks, for callers that do not need route/withheld."""
    return structural_retrieve(query, mode=mode)[0]


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

    print("structural_retrieve")

    # ── key parsing ─────────────────────────────────────────────────────────
    check(_section_of_key("ACT:COMPANIES_ACT_2013:S173") == "173",
          "section number parses out of a provision key")
    check(_section_of_key("RULE:COMPANIES_MEETINGS_BOARD_POWERS_2014:R56") is None,
          "a rule key yields no Act section number")

    # ── an exact citation returns that section's structural chunks ──────────
    chunks, route, withheld = structural_retrieve("s.173")
    from checker.retrieve import ROUTE_EXACT
    check(route == ROUTE_EXACT, f"an exact citation takes the exact route ({route})")
    check(len(chunks) >= 1, f"s.173 returns structural chunks ({len(chunks)})")
    check(all(c.section == "173" for c in chunks),
          "every returned chunk belongs to s.173")
    check(all(c.path.startswith("173") for c in chunks),
          "every chunk carries a s.173 structural path")
    check(all(c.sha256.startswith("sha256:") for c in chunks),
          "every returned chunk carries its content hash")

    # ── the citation-betrayal cases retrieve() refuses stay refused here ────
    for q in ("rule 4", "r.56", "s.9999", "section 11"):
        cs, r, _ = structural_retrieve(q)
        check(r == ROUTE_ABSTAIN and cs == [],
              f"{q!r} abstains and returns no chunks (never a near-miss)")

    # ── the small-company limbs are reachable through a citation ────────────
    cs2, r2, _ = structural_retrieve("s.2")
    paths2 = {c.path for c in cs2}
    if r2 == ROUTE_ABSTAIN:
        # s.2 may be withheld in MODE_MODEL if unadmitted; that is a valid state,
        # but then MODE_REVIEW (which shows a human everything) must surface it.
        cs2r, r2r, _ = structural_retrieve("s.2", mode="review")
        paths2 = {c.path for c in cs2r}
        check(r2r != ROUTE_ABSTAIN, "s.2 is at least reachable in review mode")
    check("2(85)(i)" in paths2 and "2(85)(ii)" in paths2,
          f"the small-company (i)/(ii) limbs are retrievable as chunks ({'2(85)(i)' in paths2})")

    # ── no duplicate paths in a result ──────────────────────────────────────
    dup_paths = [c.path for c in cs2]
    check(len(dup_paths) == len(set(dup_paths)), "no chunk path is returned twice")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
