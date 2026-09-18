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
            "insufficient_evidence": d["insufficient_evidence"]}


def _figure(key: str, as_of: date) -> dict:
    t = pt.lookup(key, as_of)
    return {"key": key, "amount": str(t.amount), "rupees": t.amount.rupees,
            "instrument": t.instrument, "effective_from": t.effective_from.isoformat(),
            "effective_to": t.effective_to.isoformat() if t.effective_to else None,
            "evidence_state": t.state, "source_url": t.source_url}


# ── citations: section and subsection, never a prefix ─────────────────────────
_CITE = re.compile(r"(?:\bs\.|\bsection\s+|\bsec\.?)\s*(\d+[A-Z]?)((?:\s*\([0-9A-Za-z]+\))*)",
                   re.I)


def canon(text: str) -> list[tuple[str, str]]:
    """Every Act citation in a string, as (section, subsection path).

    "Companies Act 2013, s.2(85)" and "section 2(85)" are both ("2", "(85)"). A bare
    number ("85", "2013") is not a citation and yields nothing.
    """
    return [(m.group(1).upper(), re.sub(r"\s+", "", m.group(2)).lower())
            for m in _CITE.finditer(text)]


def cites(provision: str, cite: str) -> bool:
    """Does an obligation's provision fall under a citation the request named?

    Same section, and one subsection path containing the other: s.173 covers s.173(1), and
    s.2(85)(i) falls under the row for s.2(85). s.16 never matches s.186, and s.2(41) never
    matches s.2(85) -- a provision number is never a prefix.
    """
    return any(n1 == n2 and (p1.startswith(p2) or p2.startswith(p1))
               for n1, p1 in canon(provision) for n2, p2 in canon(cite))


def section_of(ref: str) -> str | None:
    """The Act section an evidence-pack ref names ("ACT:COMPANIES_ACT_2013:S2" -> "2")."""
    m = re.search(r"^ACT:[A-Z0-9_]+:S(\d+[A-Z]?)$", ref)
    return m.group(1).upper() if m else None


def figure_sections(key: str) -> set[str]:
    """The Act sections a prescribed figure rests on, from the threshold table itself.

    A prescribed amount is set by a delegated instrument; the statutory bounds of the same
    family ("small_company.turnover.*") are keyed to the Act's own limb, s.2(85)(ii). That
    is the provision the figure rests on, and the only one it may be cited under.
    """
    family = key.rsplit(".", 1)[0]
    return {n for t in pt.all_thresholds() if t.key.rsplit(".", 1)[0] == family
            for n, _ in canon(t.instrument)}
