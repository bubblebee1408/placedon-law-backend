"""What `/v1/ask` reads from the engine, and how a citation is compared with another.

Split from `checker/ask.py` so the state mapping there stays readable. Everything here is a
deterministic reader: retrieval and the evidence pack, the prescribed-threshold table, and the
citation grammar. Tested through `checker/ask.py`'s suite, which drives every reader through
`answer()`.
"""
from __future__ import annotations

import re
from datetime import date

from checker import prescribed_thresholds as pt
from checker.retrieve import retrieve


def _as_json(v):
    """What the engine returned, in JSON types. A tuple becomes a list; a string stays a
    string -- list() on a string is how a sentence becomes 455 characters."""
    return list(v) if isinstance(v, tuple) else v


# ── engine readers ────────────────────────────────────────────────────────────
def _pack(query: str) -> tuple[dict, str]:
    pack, route = retrieve(query)
    return pack.to_dict(), route


def _citation(p: dict) -> dict:
    return {"ref": p["ref"], "cite": p["cite"], "title": p["title"],
            "evidence_state": p["evidence_state"],
            "usable_for_answering": p["usable_for_answering"],
            "unusable_reason": p["unusable_reason"] or None,
            "defects": p["defects"],
            "retrieved_on": sorted({s["retrieved_on"] for s in p["sources"]
                                    if s.get("retrieved_on")}),
            "source_url": next((s["source_url"] for s in p["sources"]
                                if s.get("source_url")), None)}


def _law_version(d: dict) -> dict:
    a = d["as_of"]
    return {k: a[k] for k in ("basis", "point_in_time_verified", "corpus_fetched",
                              "statement")}


def _law_version_at(provisions: list[str], requested: str) -> dict:
    """The engine's own basis statement for a past date, over the provisions a turn cites.

    Built by evidence_pack's statement builder, never written here: it is the sentence that
    says no statement is about the law as it stood on that date.
    """
    from checker import evidence_pack
    sections = sorted({m for p in provisions for m in re.findall(r"s\.(\d+[A-Z]?)", p)},
                      key=lambda x: (int(re.match(r"\d+", x).group()), x))
    pack, _ = _pack(" and ".join(f"s.{n}" for n in sections))
    fetched = tuple(pack["as_of"]["corpus_fetched"])
    a = evidence_pack._build_as_of(fetched, date.fromisoformat(requested)).to_dict()
    return {k: a[k] for k in ("basis", "point_in_time_verified", "point_in_time_requested",
                              "corpus_fetched", "statement")}


def _pack_summary(d: dict, route: str) -> dict:
    return {"retrieval_query": d["query"], "route": route, "usable_keys": d["usable_keys"],
            "unusable_keys": d["unusable_keys"], "missing": d["missing"],
            "insufficient_evidence": d["insufficient_evidence"],
            # Additive. "" whenever the route did not abstain, so the type never varies.
            "abstain_reason": d.get("abstain_reason", ""),
            # Which abbreviations were expanded. Never silent (move 4).
            "query_expansions": d.get("query_expansions", [])}


def _figure(key: str, as_of: date) -> dict:
    t = pt.lookup(key, as_of)
    return {"key": key, "amount": str(t.amount), "rupees": t.amount.rupees,
            "instrument": t.instrument, "effective_from": t.effective_from.isoformat(),
            "effective_to": t.effective_to.isoformat() if t.effective_to else None,
            "evidence_state": t.state, "source_url": t.source_url}


# ── citations: ONE grammar, the retriever's own ───────────────────────────────
# legal_retrieval._scan is how retrieve() reads a citation. Parsing it a second way here is
# what let "s 2(85)", "u/s 2(85)", "S 2 (85)", "ss. 2(85)" and "§ 2(85)" retrieve s.2 while
# matching no row -- the decided row dropped and the turn said nothing rested on it. So the
# comparison below uses the same scanner, and a provision it cannot scan is refused (a 400)
# rather than accepted and silently missed.
from checker.legal_retrieval import ACT, _ITEM, _PREFIX, _scan  # noqa: E402

# The only instrument a provision may name besides its own citation is the held Act.
_HELD_BEFORE = re.compile(r"(?:the\s+)?Companies\s+Act(?:\s*,?\s*2013)?\s*,?\s*", re.I)
_HELD_AFTER = re.compile(r"\s*,?\s*(?:(?:of|under)\s+)?(?:the\s+)?Companies\s+Act"
                         r"(?:\s*,?\s*2013)?\s*", re.I)
_US = re.compile(r"u/(?=s\b)", re.I)                 # "u/s 2(85)": the scanner reads the "s"


def not_one_citation(item: str) -> str | None:
    """Why this item is not exactly ONE Companies Act citation -- or None when it is.

    Read whole, with the retriever's own prefix and number grammar: one citation
    ("s.2(85)", "section 173(1)", "u/s 2(85)", "§ 2(85)", "rule 2(1)(t)"), optionally
    qualified by the held Act ("of the Companies Act, 2013") and by nothing else. A second
    citation, a range, or another instrument's name is refused rather than read: the scanner
    keeps only the numbers, so "section 2(85) of the LLP Act" became Companies Act s.2(85)
    and "s.2(85) and s.62" let one row stand for two citations.
    """
    text = item.strip().rstrip(".").strip()
    held = _HELD_BEFORE.match(text)
    rest = _US.sub("", text[held.end():] if held else text, count=1)
    pre = _PREFIX.match(rest)
    if not pre:
        return "it does not begin with a citation (s., section, §, rule)"
    num = _ITEM.match(rest, pre.end())
    if not num:
        return "no provision number follows the prefix"
    tail = rest[num.end():]
    if pre.group("rule") and (held or tail.strip()):
        return ("a rule is cited by its number alone; a named Rules instrument is not "
                "read here")
    if tail.strip() and (held or not _HELD_AFTER.fullmatch(tail)):
        return (f"after the citation it says {tail.strip()!r} -- a second citation, a range "
                f"or another instrument")
    return None


def canon(text: str) -> list[tuple[str, str]]:
    """Every Act citation in a string, as (section, subsection path), by the retriever's
    grammar. "Companies Act 2013, s.2(85)", "u/s 2(85)" and "§ 2 (85)" are all ("2", "(85)").
    A bare number ("85", "2013") is not a citation and yields nothing; a Rules citation is
    not an Act section and yields nothing here either."""
    return [(c.number.upper(), c.subsection.lower()) for c in _scan(text) if c.namespace == ACT]


def within(a: tuple[str, str], b: tuple[str, str]) -> bool:
    """Same section, and one clause path containing the other: s.173 and s.173(1) meet;
    s.16 and s.186 never do, nor s.2(41) and s.2(85). Paths end in ')' so a string
    prefix is a clause prefix: "(8)" is not a prefix of "(85)"."""
    return a[0] == b[0] and (a[1].startswith(b[1]) or b[1].startswith(a[1]))


def cites(provision: str, cite: str) -> bool:
    """Does an obligation's provision fall under a citation the request named?"""
    return any(within(a, b) for a in canon(provision) for b in canon(cite))


def section_of(ref: str) -> str | None:
    """The Act section an evidence-pack ref names ("ACT:COMPANIES_ACT_2013:S2" -> "2")."""
    m = re.search(r"^ACT:[A-Z0-9_]+:S(\d+[A-Z]?)$", ref)
    return m.group(1).upper() if m else None


def figure_basis(key: str) -> list[tuple[str, str]]:
    """The Act clauses a prescribed figure rests on, from the threshold table itself.

    A prescribed amount is set by a delegated instrument; the statutory bounds of the same
    family ("small_company.turnover.*") are keyed to the Act's own limb, s.2(85)(ii). That
    is the clause the figure rests on, and the only one it may be cited under.
    """
    family = key.rsplit(".", 1)[0]
    return sorted({c for t in pt.all_thresholds() if t.key.rsplit(".", 1)[0] == family
                   for c in canon(t.instrument)})
