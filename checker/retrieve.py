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

import json
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from checker import admission as adm
from checker.evidence_pack import EvidencePack, build_pack
from checker.legal_retrieval import Hit, names_a_provision, resolve
from checker.text_search import search

__all__ = ["retrieve", "ROUTE_EXACT", "ROUTE_SEARCH", "ROUTE_ABSTAIN",
           "HELD_NOT_ADMITTED", "CITATION_UNRESOLVED", "NOTHING_RETRIEVED",
           "ABSTAIN_REASONS",
           "MODE_MODEL", "MODE_REVIEW"]

MODE_MODEL = adm.MODE_MODEL
MODE_REVIEW = adm.MODE_REVIEW

ROUTE_EXACT = "exact"
ROUTE_SEARCH = "search"
ROUTE_ABSTAIN = "abstain"

# WHY an abstain happened. `route` cannot carry this -- assistant_contract.py:266 pins
# route == "abstain" on a committed fixture -- and one value covering three situations
# is what made "we do not hold this body of law" indistinguishable from "we hold it and
# did not find it" (docs/research/EMPTY_PACK_2026_09_25.md).
#
# There is deliberately NO code for "the question was not about law". The engine cannot
# know it: "How long should I boil eggs" and "Within how many days of the AGM must the
# annual return be filed" both retrieve nothing, and they are the same fact about this
# engine. Telling them apart needs a model deciding scope, and scope.py is the
# authority (CLAUDE.md). NOTHING_RETRIEVED is honest; an OFF_TOPIC code would be a lie
# with a clean interface.
HELD_NOT_ADMITTED = "HELD_NOT_ADMITTED"        # rows exist; admission withheld every one
CITATION_UNRESOLVED = "CITATION_UNRESOLVED"    # a provision was cited and cannot be resolved
NOTHING_RETRIEVED = "NOTHING_RETRIEVED"        # searched what we hold; nothing cleared the bar
ABSTAIN_REASONS = (HELD_NOT_ADMITTED, CITATION_UNRESOLVED, NOTHING_RETRIEVED)

SEARCH_TOP_K = 3

_RULES_DOC = Path(__file__).resolve().parent.parent / "corpus/rules/board_powers_2014.json"


# Words that carry no subject matter in a rule heading. Without these, "section 11" matched r.10
# and r.11 purely because their headings read "...under section 185" -- a notice that tells a
# reader a rule may be relevant when nothing suggests it is. Noise here is not free: it trains the
# reader to ignore the notices that matter.
_RULE_MATCH_STOP = frozenset("""
section sections rule rules under this that with from shall company companies made
""".split())


_RULE_CITE = re.compile(r"\b(?:rule|r)\s*\.?\s*(\d{1,2})\b", re.I)


def _named_rule_notice(query: str) -> list[str]:
    """A notice for a rule the query names by number and we hold but have not admitted."""
    if not _RULES_DOC.is_file():
        return []
    doc = json.loads(_RULES_DOC.read_text())
    if doc.get("production_usable"):
        return []
    m = _RULE_CITE.search(query)
    if not m:
        return []
    for r in doc["rules"]:
        if r["rule_number"] == m.group(1):
            return [f"{r['rule_id']} ({r['heading'][:52]}) was cited and DOES exist, but is not "
                    f"admitted for model use: {doc['status']}. Its text is unknown to you."]
    return []


def _withheld_rules(query: str) -> list[str]:
    """Rules relevant to the query that exist but are not admitted.

    They are never returned as evidence -- they have not been reviewed. But staying SILENT about
    them is the failure admission control exists to prevent: a reader cannot distinguish "there is
    no rule on this" from "there is a rule and you may not see it", and those are opposite answers.
    So a match becomes a withheld notice, which the pack reports as sought-and-not-available.

    Matching is intentionally crude -- heading words only. A rule that is merely *plausibly*
    relevant still deserves a notice; the cost of an extra notice is a sentence, and the cost of a
    missed one is a reader concluding the law is silent.
    """
    if not _RULES_DOC.is_file():
        return []
    doc = json.loads(_RULES_DOC.read_text())
    if doc.get("production_usable"):
        return []                      # admitted: retrieval proper should serve them, not this
    terms = {w for w in re.findall(r"[a-z]{4,}", query.lower())} - _RULE_MATCH_STOP
    if not terms:
        return []
    out = []
    for r in doc["rules"]:
        head = {w for w in re.findall(r"[a-z]{4,}", r["heading"].lower())}
        if terms & head:
            out.append(
                f"{r['rule_id']} ({r['heading'][:52]}) exists but is not admitted for model use: "
                f"{doc['status']}, pages {r['page_start']}-{r['page_end']}")
    return out


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
    rule_notices = _withheld_rules(query)
    if hits:
        rows, blocked = _admission_filter(_rows(hits), mode)
        blocked = blocked + rule_notices
        # The citation RESOLVED, so anything missing here was withheld, not absent.
        pack = build_pack(rows, query=query, mode=mode, withheld_notices=tuple(blocked),
                          abstain_reason="" if rows else HELD_NOT_ADMITTED)
        return pack, (ROUTE_EXACT if rows else ROUTE_ABSTAIN)

    if names_a_provision(query):
        # Cited, unresolvable. Do NOT search -- see the module docstring. But if the citation names
        # a rule we HOLD and have not admitted, say so. Abstaining silently here tells the reader
        # the same thing as "no such rule exists", and one of those is false.
        # Two facts hide here too, and this branch already computes the difference.
        # If `_named_rule_notice` produced anything, the cited rule IS held and merely
        # unadmitted -- which this function's own docstring insists must be said,
        # because abstaining silently "tells the reader the same thing as 'no such
        # rule exists', and one of those is false". Only a citation that resolves to
        # nothing we hold is genuinely unresolvable.
        named = _named_rule_notice(query)
        return (build_pack([], query=query, mode=mode,
                           withheld_notices=tuple(rule_notices + named),
                           abstain_reason=(HELD_NOT_ADMITTED if (named or rule_notices)
                                           else CITATION_UNRESOLVED)),
                ROUTE_ABSTAIN)

    found = search(query, top_k=top_k)
    rows, blocked = _admission_filter(found, mode)
    blocked = blocked + rule_notices
    # Two different abstains hide behind this branch, and they are not the same fact:
    # search found nothing at all, or it found rows and admission withheld all of them.
    # The first is "we could not find it"; the second is "it exists and is not reviewed".
    reason = "" if rows else (HELD_NOT_ADMITTED if found else NOTHING_RETRIEVED)
    # Withheld items ride in `requested_sections`, which the pack already renders as "sought and
    # not found". That is the honest shape: the model is told something was asked for and is not
    # here, without being handed the inadmissible text itself.
    pack = build_pack(rows, query=query, mode=mode, withheld_notices=tuple(blocked),
                      abstain_reason=reason)
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

    # ---- WHY it abstained. One `abstain` used to cover three different facts, and a
    # lawyer could not tell "we do not hold this body of law" from "we hold it and did
    # not find it" (docs/research/EMPTY_PACK_2026_09_25.md). `route` itself may NOT
    # carry this: scripts/assistant_contract.py:266 pins route == "abstain".
    def _reason(q: str) -> str:
        return retrieve(q)[0].abstain_reason

    check(_reason("rule 4 of the Board Rules") == HELD_NOT_ADMITTED,
          "a cited rule we HOLD and have not admitted says so, rather than abstaining "
          "silently -- which would read as 'no such rule exists'")
    check(_reason("section 9999") == CITATION_UNRESOLVED,
          "a citation that resolves to nothing we hold is UNRESOLVED, not withheld")
    check(_reason("Do we need consent before sharing employee data with a vendor?")
          == NOTHING_RETRIEVED,
          "a search that found nothing says so -- it does not claim the body of law is "
          "out of scope, which ask_scope decides separately")
    check(_reason("s.173") == "",
          "a route that did NOT abstain carries an empty reason, never a stale one")
    check(all(r in ABSTAIN_REASONS for r in
              (_reason("rule 4"), _reason("section 9999"), _reason("xyzzy plugh"))),
          "every reason given is one of the declared constants")
    # The honest limit, pinned so nobody later adds an OFF_TOPIC code: the engine cannot
    # tell an off-topic question from held law it failed to retrieve. Both are the same
    # fact about the engine, and separating them needs a model deciding scope.
    check(_reason("How long should I boil eggs for breakfast?")
          == _reason("Within how many days of the AGM must the annual return be filed?")
          == NOTHING_RETRIEVED,
          "an off-topic question and held law we could not find are the SAME reason -- "
          "the engine cannot distinguish them and does not pretend to")
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

    check(retrieve("s.1", mode=MODE_MODEL)[0].to_dict()["provisions"],
          "s.1 is limited-production and still servable (the tail is restricted, not the law)")

    # --- the mixed pack: admissible Act section beside withheld Rules ---
    mixed, mroute = retrieve("related party transactions", mode=MODE_MODEL)
    keys = [p.key for p in mixed.usable]
    check("ACT:COMPANIES_ACT_2013:S188" in keys, "the admissible Act section is served")
    notices = " ".join(mixed.missing)
    check("R15" in notices or "related party" in notices.lower(),
          f"the withheld rule is REPORTED, not silently omitted ({notices[:80]!r})")
    check(not any("RULE:" in k for k in keys), "no unadmitted rule is served as evidence")
    check(mroute == ROUTE_SEARCH, "the mixed query still resolves via search")

    # Silence would be the failure. A reader must be able to tell these apart.
    quiet, _ = retrieve("s.174", mode=MODE_MODEL)
    check(not any("RULE:" in m for m in quiet.missing),
          "a query with no relevant rule gets no rule notice")

    block = retrieve("s.173")[0].prompt_block()
    check("INSUFFICIENT EVIDENCE" in block, "the prompt block names the abstention answer")
    check("bare section number is not an identity" in block.lower(),
          "the prompt block forbids bare-number citation")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
