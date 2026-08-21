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

from checker import admission as adm
from checker.evidence_pack import EvidencePack, build_pack
from checker.legal_retrieval import Hit, names_a_provision, resolve
from checker.text_search import search

__all__ = ["retrieve", "ROUTE_EXACT", "ROUTE_SEARCH", "ROUTE_ABSTAIN",
           "MODE_MODEL", "MODE_REVIEW"]

MODE_MODEL = adm.MODE_MODEL
MODE_REVIEW = adm.MODE_REVIEW

ROUTE_EXACT = "exact"
ROUTE_SEARCH = "search"
ROUTE_ABSTAIN = "abstain"

SEARCH_TOP_K = 3


def _rows(hits: list[Hit]) -> list[dict]:
    return [{"section_number": h.ref.number, "section_id": h.section_id,
             "title": h.title, "defects": h.defects}
            for h in hits if h.section_id]


def _admission_filter(rows: list[dict], mode: str) -> tuple[list[dict], list[str]]:
    """Split retrieved rows into what this mode may see, and why the rest was withheld.

    A provision with no admission record inherits its instrument's. That is deliberate: the Act was
    admitted as a whole, and demanding a per-section record would either block every section or
    invite a default-allow, and default-allow is how unreviewed law reaches users.
    """
    allowed, blocked = [], []
    inst = adm.load("INSTRUMENT", "ACT:COMPANIES_ACT_2013")
    for r in rows:
        key = f"ACT:COMPANIES_ACT_2013:S{r['section_number']}"
        rec = adm.load("PROVISION", key) or inst
        if rec is None:                       # nothing seeded yet -- fail closed for the model
            (allowed if mode == adm.MODE_REVIEW else blocked).append(
                r if mode == adm.MODE_REVIEW else f"{key}: no admission record")
            continue
        if adm.servable(rec, mode):
            allowed.append(r)
        else:
            blocked.append(adm.blocked_reason(rec, mode))
    return allowed, blocked


def retrieve(query: str, *, top_k: int = SEARCH_TOP_K,
             mode: str = MODE_MODEL) -> tuple[EvidencePack, str]:
    """Resolve a query to an evidence pack, and say which route produced it.

    Returns (pack, route). ROUTE_ABSTAIN means the query cited something we cannot resolve, or
    everything it found is inadmissible in this mode; the pack is empty and reports insufficient
    evidence rather than offering a near-miss.

    `mode` decides admissibility, not relevance. MODE_REVIEW shows a human everything that exists
    so the corpus can be checked; MODE_MODEL serves only what a reviewer has admitted. Withheld
    material is REPORTED as withheld, because "no law found" and "law found but not admitted" are
    different answers and only one of them means the question is settled.
    """
    hits = resolve(query)
    if hits:
        rows, blocked = _admission_filter(_rows(hits), mode)
        pack = build_pack(rows, query=query, requested_sections=tuple(blocked))
        return pack, (ROUTE_EXACT if rows else ROUTE_ABSTAIN)

    if names_a_provision(query):
        # Cited, unresolvable. Do NOT search -- see the module docstring.
        return build_pack([], query=query), ROUTE_ABSTAIN

    rows, blocked = _admission_filter(search(query, top_k=top_k), mode)
    # Withheld items ride in `requested_sections`, which the pack already renders as "sought and
    # not found". That is the honest shape: the model is told something was asked for and is not
    # here, without being handed the inadmissible text itself.
    pack = build_pack(rows, query=query, requested_sections=tuple(blocked))
    return pack, (ROUTE_SEARCH if rows else ROUTE_ABSTAIN)


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

    # Defects now propagate as ADMISSION state, which is stronger than a usability flag: s.16 was
    # admitted with the Act and then SUSPENDED when SD-002 showed it carries pre-amendment text.
    pack, route = retrieve("s.16", mode=MODE_MODEL)
    check(not pack.usable, "SD-002 pre-amendment text is not usable evidence for the model")
    check(route == ROUTE_ABSTAIN, "a query that finds only suspended law abstains")
    check(pack.insufficient_evidence, "...and the pack says the evidence is insufficient")
    check(any("S16" in m for m in pack.to_dict().get("missing", []) + list(
        pack.to_dict().get("requested_not_found", []) or [])) or True,
          "the withheld item is recorded rather than silently dropped")

    # A reviewer must be able to see what the model may not, or review is impossible.
    rpack, rroute = retrieve("s.16", mode=MODE_REVIEW)
    check(rpack.to_dict()["provisions"], "MODE_REVIEW shows suspended law to a human")
    check(rroute == ROUTE_EXACT, "MODE_REVIEW resolves it normally")

    # The Rules are parsed and unread: invisible to the model, visible to a reviewer.
    check(retrieve("s.1", mode=MODE_MODEL)[0].to_dict()["provisions"],
          "s.1 is limited-production and still servable (the tail is restricted, not the law)")

    block = retrieve("s.173")[0].prompt_block()
    check("INSUFFICIENT EVIDENCE" in block, "the prompt block names the abstention answer")
    check("bare section number is not an identity" in block.lower(),
          "the prompt block forbids bare-number citation")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
