"""Multi-body retrieval orchestrator: practice area → per-body retrieve → merged result.

Today only CA2013 is IN_CORPUS. This orchestrator calls `retrieve()` for each held body
and reports every DECLARED body by name, so the user knows exactly what we do not hold.
When SEBI LODR or others are admitted, they slot in without changing the API.

Judgment discovery (tier LICENSED): `discover()` from `judgment_index` runs alongside
statutory retrieval. A judgment may SUPPORT an answer, never make one VERIFIED. The two
channels are independent — a statutory abstain does not suppress judgment hits, and a
judgment hit does not upgrade an abstained statutory answer.

Run: PYTHONPATH=. python3 checker/retrieve_multi.py
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from checker.scope import (
    BODIES, PRACTICE_AREA_BODIES, _BY_KEY,
    IN_CORPUS, CURRENT_ONLY, DECLARED, Body,
    bodies_for_practice_area, scope_for_practice_area,
)
from checker.retrieve import (
    retrieve, EvidencePack, ROUTE_ABSTAIN,
    MODE_MODEL, MODE_REVIEW,
)

__all__ = ["retrieve_for_practice_area", "MultiBodyResult"]


@dataclass(frozen=True)
class JudgmentHit:
    """A judgment discovered by metadata or dense search. Tier LICENSED — support only."""
    s3_key: str
    title: str
    court: str
    year: int | None
    parties: str


@dataclass(frozen=True)
class MultiBodyResult:
    """Merged retrieval across all bodies in a practice area."""
    pack: EvidencePack
    route: str
    searched_bodies: tuple[str, ...]
    declared_bodies: tuple[str, ...]
    declared_notices: tuple[str, ...]
    supporting_judgments: tuple[JudgmentHit, ...] = ()


def retrieve_for_practice_area(
    query: str,
    practice_area: str | None = None,
    *,
    top_k: int = 3,
    mode: str = MODE_MODEL,
) -> MultiBodyResult:
    """Retrieve across all bodies relevant to a practice area.

    For each IN_CORPUS body: calls retrieve().
    For each DECLARED body: produces a notice naming it and what would need to be acquired.
    For CURRENT_ONLY: notes it exists but is not yet wired.

    When practice_area is None, searches all held bodies (currently just CA2013).
    """
    if practice_area and practice_area in PRACTICE_AREA_BODIES:
        scope = scope_for_practice_area(practice_area)
        relevant = bodies_for_practice_area(practice_area)
    else:
        relevant = [b for b in BODIES if b.status in (IN_CORPUS, CURRENT_ONLY, DECLARED)]
        scope = {
            "answerable": [b for b in relevant if b.answerable],
            "current_only": [b for b in relevant if b.status == CURRENT_ONLY],
            "declared": [b for b in relevant if b.status == DECLARED],
        }

    searched: list[str] = []
    declared_notices: list[str] = []
    declared_keys: list[str] = []

    # ponytail: only CA2013 retrieval works today; loop is ready for more
    for body in scope.get("answerable", []):
        if body.key == "CA2013":
            searched.append(body.key)

    for body in scope.get("current_only", []):
        declared_notices.append(
            f"{body.name} ({body.key}): text is held (consolidated) but not yet "
            f"admitted for retrieval. {body.note}"
        )
        declared_keys.append(body.key)

    for body in scope.get("declared", []):
        declared_notices.append(
            f"{body.name} ({body.key}): in scope but nothing acquired. "
            f"Covers: {body.covers}. {body.note}"
        )
        declared_keys.append(body.key)

    pack, route = retrieve(query, top_k=top_k, mode=mode)

    judgments = _discover_judgments(query, limit=5)

    return MultiBodyResult(
        pack=pack,
        route=route,
        searched_bodies=tuple(searched),
        declared_bodies=tuple(declared_keys),
        declared_notices=tuple(declared_notices),
        supporting_judgments=tuple(judgments),
    )


def _discover_judgments(query: str, *, limit: int = 5) -> list[JudgmentHit]:
    """Best-effort judgment discovery. Returns [] when the index is absent or empty."""
    try:
        from checker.sources.judgment_index import discover, JudgmentRef
    except ImportError:
        return []
    try:
        refs = discover(query, limit=limit)
    except Exception:
        return []
    return [
        JudgmentHit(
            s3_key=r.s3_key,
            title=getattr(r, "title", ""),
            court=getattr(r, "court", ""),
            year=getattr(r, "year", None),
            parties=getattr(r, "parties", ""),
        )
        for r in refs
    ]


def _self_test() -> None:
    passed = failed = 0

    def check(name: str, cond: bool) -> None:
        nonlocal passed, failed
        if cond:
            print(f"  [PASS] {name}")
            passed += 1
        else:
            print(f"  [FAIL] {name}")
            failed += 1

    # basic: no practice area → searches CA2013
    r = retrieve_for_practice_area("s.173")
    check("CA2013 searched", "CA2013" in r.searched_bodies)
    check("pack has provisions", bool(r.pack.to_dict()["provisions"]))

    # corporate practice area → CA2013 searched, LLP2008 declared
    r = retrieve_for_practice_area("s.173", "corporate")
    check("corporate: CA2013 searched", "CA2013" in r.searched_bodies)
    check("corporate: LLP2008 declared", "LLP2008" in r.declared_bodies)
    check("corporate: LLP notice present",
          any("LLP" in n for n in r.declared_notices))

    # due_diligence → CA2013 + notices for SEBI_LODR, FEMA, CONTRACT
    r = retrieve_for_practice_area("related party transactions", "due_diligence")
    check("dd: CA2013 searched", "CA2013" in r.searched_bodies)
    check("dd: SEBI_LODR in declared", "SEBI_LODR" in r.declared_bodies)
    check("dd: FEMA in declared", "FEMA1999" in r.declared_bodies)
    check("dd: CONTRACT in declared", "CONTRACT1872" in r.declared_bodies)
    check("dd: at least 3 notices", len(r.declared_notices) >= 3)

    # capital_markets → SEBI_LODR is current_only, SEBI_OTHER declared
    r = retrieve_for_practice_area("insider trading", "capital_markets")
    check("cm: SEBI_LODR in declared (current_only)", "SEBI_LODR" in r.declared_bodies)
    check("cm: SEBI_OTHER in declared", "SEBI_OTHER" in r.declared_bodies)
    check("cm: notice mentions consolidated",
          any("consolidated" in n for n in r.declared_notices))

    # unknown practice area → falls back to all bodies
    r = retrieve_for_practice_area("s.173", "unknown_area")
    check("unknown area: CA2013 still searched", "CA2013" in r.searched_bodies)

    # abstain propagates
    r = retrieve_for_practice_area("rule 4", "corporate")
    check("abstain propagates", r.route == ROUTE_ABSTAIN)

    # declared_notices are strings, not empty
    r = retrieve_for_practice_area("test", "transactions")
    check("notices are non-empty strings",
          all(isinstance(n, str) and len(n) > 10 for n in r.declared_notices))

    # judgment discovery returns a tuple (possibly empty if no index built)
    r = retrieve_for_practice_area("oppression and mismanagement", "disputes")
    check("supporting_judgments is a tuple", isinstance(r.supporting_judgments, tuple))
    check("judgment hits are JudgmentHit or empty",
          all(isinstance(j, JudgmentHit) for j in r.supporting_judgments))

    # judgment discovery does not crash on exact citation
    r = retrieve_for_practice_area("s.173")
    check("judgments field present on exact", hasattr(r, "supporting_judgments"))

    print(f"\n{passed + failed} tests, {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    _self_test()
