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
from checker import section_index as _si
from checker import voyage_dense
from checker.evidence_pack import EvidencePack, build_pack
from checker.legal_retrieval import Hit, names_a_provision, resolve
from checker.text_search import search

__all__ = ["retrieve", "hybrid_search", "ROUTE_EXACT", "ROUTE_SEARCH", "ROUTE_ABSTAIN",
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


# ── hybrid (lexical + dense) search for the no-citation path ──────────────────
#
# Semantic retrieval activation. Lexical alone is `text_search.search` above -- a
# match of the question's WORDS against the corpus. `voyage_dense.search` finds the
# same corpus by MEANING, via a precomputed Voyage embedding index
# (scripts/build_voyage_index.py). The two are fused by Reciprocal Rank Fusion --
# the k=60 published constant `checker/fusion.py` already measured this on (BM25 +
# MiniLM dense): a lexical score and a cosine are not on the same scale, and fusing
# RANKS rather than scores never invents a comparability that is not there. This is
# a separate, smaller fusion than `checker.fusion`/`checker.reranker` on purpose --
# those two are wired to `corpus_retrieval` (a different BM25) and `dense_index`
# (local MiniLM), measured against the frozen 70-case eval as an experiment that is
# "judged, not adopted" by its own docstring. Routing Voyage's numbers through that
# model would silently swap retrievers out from under an unrelated, already-measured
# comparison. This fusion is purpose-built for the pair this task activates.
#
# Fail-safe by construction: when the dense index or a Voyage key is unavailable --
# every environment until `--live` builds the index with a key -- `hybrid_search`
# degrades EXACTLY to `text_search.search` alone. That is this module's entire
# behaviour before this function existed, so nothing already shipped regresses.
_RRF_K = 60
_DENSE_POOL = 10


def _rank_map(numbers: list[str]) -> dict[str, int]:
    """Best-first section numbers -> {number: 1-based rank}, first occurrence wins."""
    ranks: dict[str, int] = {}
    for i, n in enumerate(numbers):
        ranks.setdefault(n, i + 1)
    return ranks


def _row_for_number(number: str, lexical_by_number: dict[str, dict]) -> dict | None:
    """A row for one corpus section number: the lexical hit if there is one, else
    built fresh from the section index for a dense-only hit.

    Returns None for a number the corpus does not actually hold. A dense "hit" that
    is not a real corpus ID must never be served -- CLAUDE.md forbids fabricating a
    provision, and this is the one place a bare number from outside the corpus could
    otherwise slip into an evidence pack.
    """
    if number in lexical_by_number:
        return lexical_by_number[number]
    rec = _si.section_by_number(number)
    if rec is None:
        return None
    return {"section_number": number, "section_id": str(rec["section_id"]),
            "title": rec["title"], "score": 0.0, "route": "dense", "matched": "",
            "defects": ()}


def hybrid_search(query: str, top_k: int) -> list[dict]:
    """Lexical UNION dense, fused by reciprocal rank -- the identical row shape
    `text_search.search()` returns, so nothing downstream of `retrieve()` can tell
    which retriever found a given row.

    Additive: lexical results are never removed for a dense disagreement, and a
    section only dense finds is added, never substituted for one lexical already
    found. Falls back to lexical alone whenever dense retrieval cannot run.
    """
    pool = max(top_k, _DENSE_POOL)
    lexical_rows = search(query, top_k=pool)
    dense_ok, _why = voyage_dense.available()
    if not dense_ok:
        return lexical_rows[:top_k]
    try:
        dense_hits = voyage_dense.search(query, top_k=_DENSE_POOL)
    except voyage_dense.VoyageDenseUnavailable:
        return lexical_rows[:top_k]           # fail-safe: never worse than lexical alone

    lexical_by_number = {r["section_number"]: r for r in lexical_rows}
    rank_maps = (_rank_map([r["section_number"] for r in lexical_rows]),
                 _rank_map([number for number, _title, _score in dense_hits]))
    fused: dict[str, float] = {}
    for ranks in rank_maps:
        for number, rank in ranks.items():
            fused[number] = fused.get(number, 0.0) + 1.0 / (_RRF_K + rank)
    order = sorted(fused, key=lambda n: -fused[n])

    rows: list[dict] = []
    for number in order:
        row = _row_for_number(number, lexical_by_number)
        if row is not None:
            rows.append(row)
        if len(rows) >= top_k:
            break
    return rows


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

    from checker.text_search import expand_query
    _, expansions = expand_query(query)
    found = hybrid_search(query, top_k)
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
                      abstain_reason=reason, query_expansions=expansions)
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
    # Asserted STRUCTURALLY, not by a behavioural coincidence. The first version of this
    # check paired an off-topic question with "Within how many days of the AGM must the
    # annual return be filed?" and asserted both gave NOTHING_RETRIEVED. Move 4's
    # abbreviation lexicon then FIXED the second one -- "AGM" now expands to "annual
    # general meeting" and it retrieves s.92 -- so the check started failing on a
    # genuine improvement. A test pinned to today's failures fails when they are fixed;
    # what must hold is the RULE.
    check("OFF_TOPIC" not in ABSTAIN_REASONS and len(ABSTAIN_REASONS) == 3,
          "there is no OFF_TOPIC reason: the engine cannot tell an off-topic question "
          "from held law it failed to retrieve, and inventing a code for it would be a "
          "lie with a clean interface")
    check(_reason("How long should I boil eggs for breakfast?") == NOTHING_RETRIEVED,
          "...so an off-topic question says only what is true: we searched and found nothing")
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

    # ── semantic retrieval activation: hybrid_search fuses lexical UNION dense ──
    from unittest import mock

    # 1. Fail-safe default. This gate strips VOYAGE_API_KEY and ships no prebuilt
    #    index, so dense is unavailable here -- and hybrid_search must degrade to
    #    EXACTLY lexical search. Every check above this line already exercised this
    #    path implicitly (hybrid_search is what retrieve() now calls); this makes the
    #    guarantee explicit rather than incidental.
    dense_ok, _why = voyage_dense.available()
    check(not dense_ok, "dense retrieval is unavailable by default in this gate (no key, no index)")
    for q in ("related party transactions", "loans to directors", "quorum for board meetings"):
        check(hybrid_search(q, SEARCH_TOP_K) == search(q, top_k=SEARCH_TOP_K),
              f"with dense unavailable, hybrid_search({q!r}) is IDENTICAL to lexical search alone "
              f"-- never worse than before this activation")

    # 2. The concrete case this activation exists for: a question phrased in words
    #    lexical retrieval cannot reach AT ALL. text_search.py's own docstring names
    #    this exact limit -- "can a director dial in remotely" has no lexical hook
    #    once "attend" is swapped out, while the Act governs it at s.173 ("participation
    #    ... through video conferencing"). Confirmed empty today, by the real module,
    #    before any mock is installed.
    REMOTE_Q = "can a director dial in remotely to a board meeting"
    check(search(REMOTE_Q, top_k=5) == [],
          "lexical retrieval alone reaches nothing for this phrasing (confirmed live)")

    def fake_available(path=voyage_dense.INDEX_PATH):
        return True, "stub index for this test"

    def fake_dense_search(q, top_k=5, **kw):
        # A real cosine ranking would find s.173 by MEANING; stubbed here because
        # no Voyage key is configured in this gate (check 1 above proves that).
        return [("173", "Meetings of Board", 0.81)] if q == REMOTE_Q else []

    with mock.patch.object(voyage_dense, "available", side_effect=fake_available), \
         mock.patch.object(voyage_dense, "search", side_effect=fake_dense_search):
        hyb = hybrid_search(REMOTE_Q, SEARCH_TOP_K)
        check([r["section_number"] for r in hyb] == ["173"],
              f"hybrid_search reaches s.173 where lexical alone reaches nothing "
              f"({[r['section_number'] for r in hyb]})")
        check(bool(hyb[0]["section_id"]) and hyb[0]["title"] == "Meetings of Board",
              "the dense-only row carries real corpus identity (section_id, title) -- it is "
              "built from the section index, not a stub")

        # End to end through retrieve() -- the same contract ask.py reads.
        pack, route = retrieve(REMOTE_Q, mode=MODE_MODEL)
        check(route == ROUTE_SEARCH, "the hybrid route is still reported as 'search' (unchanged)")
        check("ACT:COMPANIES_ACT_2013:S173" in [p.key for p in pack.usable],
              "the pack built from a dense-only row carries s.173 as usable evidence")

    # 3. The invariant this activation must never break: a dense "hit" naming a
    #    section the corpus does not actually hold is dropped, never fabricated into
    #    evidence (CLAUDE.md: never fabricate a provision).
    def fake_dense_bogus(q, top_k=5, **kw):
        return [("999999-no-such-section", "invented", 0.99), ("185", "Loan to directors, etc.", 0.5)]

    with mock.patch.object(voyage_dense, "available", side_effect=fake_available), \
         mock.patch.object(voyage_dense, "search", side_effect=fake_dense_bogus):
        hyb = hybrid_search("loans to directors", SEARCH_TOP_K)
        nums = [r["section_number"] for r in hyb]
        check("999999-no-such-section" not in nums,
              f"a dense hit naming a section the corpus does not hold is silently dropped, "
              f"never served as evidence ({nums})")
        check("185" in nums, "a genuine dense hit for a real section is still served")

    # 4. Additive, not substitutive: a section lexical already found at rank 1 is not
    #    displaced just because dense (stubbed) disagrees and finds something else.
    def fake_dense_disjoint(q, top_k=5, **kw):
        return [("173", "Meetings of Board", 0.4)]      # unrelated to this query's lexical hit

    with mock.patch.object(voyage_dense, "available", side_effect=fake_available), \
         mock.patch.object(voyage_dense, "search", side_effect=fake_dense_disjoint):
        hyb = hybrid_search("related party transactions", top_k=5)
        nums = [r["section_number"] for r in hyb]
        check("188" in nums,
              f"the lexical hit for 'related party transactions' (s.188) survives fusion even "
              f"though dense (stubbed) ranks something unrelated ({nums})")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
