"""Positional playbook hierarchy: Starting → Fallback → Dealbreaker.

Layers on top of playbook.py without modifying it. A Position carries a ranked
set of acceptable stances the firm will take on a clause, from the ideal
(starting) through acceptable compromises (fallbacks) down to the line the firm
will not cross (dealbreaker).

This is what Jurisphere calls "Review Playbooks" — each rule carries a Starting
Position, ranked Fallback Positions, and a Dealbreaker Position.

The core playbook.py evaluates MATCHES/DEVIATES/MISSING/NEEDS_LAWYER against a
single value. This module resolves WHERE in the position ladder the clause lands:
STARTING, FALLBACK_N, NOT_ACCEPTABLE, or NEEDS_LAWYER.

Run: PYTHONPATH=. python3 checker/positions.py
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from checker.playbook import years, amount, NEEDS_LAWYER as _NL

__all__ = [
    "Position", "PositionRule", "PositionPlaybook",
    "resolve_position", "resolve_all",
    "STARTING", "FALLBACK", "NOT_ACCEPTABLE", "NEEDS_LAWYER",
    "MANDATORY", "RECOMMENDED", "NICE_TO_HAVE",
]

STARTING = "STARTING"
FALLBACK = "FALLBACK"
NOT_ACCEPTABLE = "NOT_ACCEPTABLE"
NEEDS_LAWYER = _NL
POSITION_STATUSES = (STARTING, FALLBACK, NOT_ACCEPTABLE, NEEDS_LAWYER)

MANDATORY = "MANDATORY"
RECOMMENDED = "RECOMMENDED"
NICE_TO_HAVE = "NICE_TO_HAVE"
PRIORITIES = (MANDATORY, RECOMMENDED, NICE_TO_HAVE)


@dataclass(frozen=True)
class Position:
    """One stance in the ladder."""
    text: str
    value: object = None


@dataclass(frozen=True)
class PositionRule:
    """A playbook rule with positional hierarchy.

    starting: the firm's ideal position
    fallbacks: ranked compromises (index 0 = most preferred)
    dealbreaker: the line the firm will not cross
    priority: MANDATORY / RECOMMENDED / NICE_TO_HAVE
    comparator: 'max_years' | 'max_amount' | 'equals' | 'in_list' — how values compare
    """
    id: str
    clause: str
    starting: Position
    fallbacks: tuple[Position, ...] = ()
    dealbreaker: Position | None = None
    priority: str = MANDATORY
    comparator: str = "equals"
    applicability: str | None = None


@dataclass(frozen=True)
class PositionResult:
    """Where a clause lands on the position ladder."""
    rule_id: str
    clause: str
    status: str
    position_index: int | None = None
    detail: str = ""
    priority: str = MANDATORY
    # ponytail: continuous confidence per Fuzzy Triage (arXiv 2603.07390)
    # 1.0 = exact comparator match, <1.0 = fuzzy, 0.0 = unknown
    confidence: float = 1.0


@dataclass(frozen=True)
class PositionPlaybook:
    id: str
    version: str
    rules: tuple[PositionRule, ...]


def _compare(comparator: str, clause_value: object, position_value: object) -> tuple[bool, float] | None:
    """Does the clause value satisfy the position? Returns (match, confidence) or None.

    Confidence is 1.0 for exact comparator matches, graded for numeric proximity.
    Per Fuzzy Triage (arXiv 2603.07390): continuous scores with thresholds are more
    principled than hard categorical assignment.
    """
    if comparator == "equals":
        match = str(clause_value).strip().lower() == str(position_value).strip().lower()
        return (match, 1.0)
    if comparator == "in_list":
        allowed = position_value if isinstance(position_value, (list, tuple)) else [position_value]
        match = str(clause_value).strip().lower() in [str(v).strip().lower() for v in allowed]
        return (match, 1.0)
    if comparator == "max_years":
        got, limit = years(clause_value), years(position_value)
        if got is None or limit is None:
            return None
        match = got <= limit
        conf = 1.0 if match else max(0.0, 1.0 - (got - limit) / max(limit, 1))
        return (match, conf)
    if comparator == "min_years":
        got, limit = years(clause_value), years(position_value)
        if got is None or limit is None:
            return None
        match = got >= limit
        conf = 1.0 if match else max(0.0, 1.0 - (limit - got) / max(limit, 1))
        return (match, conf)
    if comparator == "max_amount":
        got, limit = amount(clause_value), amount(position_value)
        if got is None or limit is None:
            return None
        match = got <= limit
        conf = 1.0 if match else max(0.0, 1.0 - (got - limit) / max(limit, 1))
        return (match, conf)
    if comparator == "min_amount":
        got, limit = amount(clause_value), amount(position_value)
        if got is None or limit is None:
            return None
        match = got >= limit
        conf = 1.0 if match else max(0.0, 1.0 - (limit - got) / max(limit, 1))
        return (match, conf)
    return None


def resolve_position(rule: PositionRule, clause_value: object | None) -> PositionResult:
    """Resolve where a clause value lands on the position ladder."""
    if clause_value is None:
        return PositionResult(rule.id, rule.clause, NEEDS_LAWYER,
                              detail="no clause value extracted", priority=rule.priority,
                              confidence=0.0)

    # check starting position
    result = _compare(rule.comparator, clause_value, rule.starting.value)
    if result is None:
        return PositionResult(rule.id, rule.clause, NEEDS_LAWYER,
                              detail="value could not be compared", priority=rule.priority,
                              confidence=0.0)
    match, conf = result
    if match:
        return PositionResult(rule.id, rule.clause, STARTING, position_index=0,
                              detail=f"meets starting position: {rule.starting.text}",
                              priority=rule.priority, confidence=conf)

    # check fallbacks in order
    for i, fb in enumerate(rule.fallbacks):
        result = _compare(rule.comparator, clause_value, fb.value)
        if result is None:
            return PositionResult(rule.id, rule.clause, NEEDS_LAWYER,
                                  detail=f"fallback {i+1} could not be compared",
                                  priority=rule.priority, confidence=0.0)
        match, conf = result
        if match:
            return PositionResult(rule.id, rule.clause, FALLBACK, position_index=i + 1,
                                  detail=f"meets fallback {i+1}: {fb.text}",
                                  priority=rule.priority, confidence=conf)

    # check dealbreaker
    if rule.dealbreaker is not None:
        result = _compare(rule.comparator, clause_value, rule.dealbreaker.value)
        if result is None:
            return PositionResult(rule.id, rule.clause, NEEDS_LAWYER,
                                  detail="dealbreaker could not be compared",
                                  priority=rule.priority, confidence=0.0)
        match, conf = result
        if not match:
            return PositionResult(rule.id, rule.clause, NOT_ACCEPTABLE,
                                  detail=f"crosses dealbreaker: {rule.dealbreaker.text}",
                                  priority=rule.priority, confidence=conf)

    # past all fallbacks but not past dealbreaker (or no dealbreaker set)
    return PositionResult(rule.id, rule.clause, NOT_ACCEPTABLE,
                          detail="below all fallback positions", priority=rule.priority,
                          confidence=1.0)


def resolve_all(playbook: PositionPlaybook, extracted: dict[str, object]) -> tuple[PositionResult, ...]:
    """Resolve every rule against extracted clause values."""
    return tuple(resolve_position(r, extracted.get(r.clause)) for r in playbook.rules)


# ── self-test ──────────────────────────────────────────────────────────────

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

    # NDA survival clause: starting 5yr, fallback 3yr, dealbreaker <1yr
    # min_years: firm wants AT LEAST this many years (longer is better)
    survival = PositionRule(
        id="NDA-SURVIVAL",
        clause="survival_period",
        starting=Position("5 years from termination", "5 years"),
        fallbacks=(
            Position("3 years if counterparty pushes", "3 years"),
            Position("2 years as absolute minimum", "2 years"),
        ),
        dealbreaker=Position("below 1 year", "1 year"),
        priority=MANDATORY,
        comparator="min_years",
    )

    # 5 years → STARTING
    r = resolve_position(survival, "five years")
    check("5yr meets starting position", r.status == STARTING)
    check("starting has index 0", r.position_index == 0)

    # 3 years → FALLBACK 1
    r = resolve_position(survival, "three years")
    check("3yr meets fallback 1", r.status == FALLBACK)
    check("fallback 1 has index 1", r.position_index == 1)

    # 2 years → FALLBACK 2
    r = resolve_position(survival, "two years")
    check("2yr meets fallback 2", r.status == FALLBACK)
    check("fallback 2 has index 2", r.position_index == 2)

    # 18 months = 1.5yr: below fallback 2 (2yr) but above dealbreaker (1yr) → NOT_ACCEPTABLE
    r = resolve_position(survival, "18 months")
    check("18mo below all fallbacks but above dealbreaker → NOT_ACCEPTABLE",
          r.status == NOT_ACCEPTABLE)

    # 6 months → NOT_ACCEPTABLE (below dealbreaker)
    r = resolve_position(survival, "6 months")
    check("6mo is NOT_ACCEPTABLE", r.status == NOT_ACCEPTABLE)
    check("detail mentions dealbreaker", "dealbreaker" in r.detail)

    # None → NEEDS_LAWYER
    r = resolve_position(survival, None)
    check("no value → NEEDS_LAWYER", r.status == NEEDS_LAWYER)

    # unreadable → NEEDS_LAWYER
    r = resolve_position(survival, "forever and ever")
    check("unreadable value → NEEDS_LAWYER", r.status == NEEDS_LAWYER)

    # equals comparator: governing law
    gov_law = PositionRule(
        id="GOV-LAW",
        clause="governing_law",
        starting=Position("Indian law, courts of Mumbai", "India"),
        fallbacks=(Position("Indian law, courts of Delhi", "India"),),
        dealbreaker=None,
        priority=RECOMMENDED,
        comparator="equals",
    )
    r = resolve_position(gov_law, "India")
    check("equals: exact match → STARTING", r.status == STARTING)
    r = resolve_position(gov_law, "Singapore")
    check("equals: mismatch with no dealbreaker → NOT_ACCEPTABLE", r.status == NOT_ACCEPTABLE)

    # in_list comparator: arbitration seat
    seat = PositionRule(
        id="ARB-SEAT",
        clause="arbitration_seat",
        starting=Position("Mumbai", ["Mumbai"]),
        fallbacks=(Position("Delhi or Bangalore", ["Delhi", "Bangalore"]),),
        dealbreaker=None,
        priority=MANDATORY,
        comparator="in_list",
    )
    r = resolve_position(seat, "Mumbai")
    check("in_list: member of starting list → STARTING", r.status == STARTING)
    r = resolve_position(seat, "Bangalore")
    check("in_list: member of fallback list → FALLBACK", r.status == FALLBACK)
    r = resolve_position(seat, "London")
    check("in_list: not in any list → NOT_ACCEPTABLE", r.status == NOT_ACCEPTABLE)

    # max_amount: liability cap
    cap = PositionRule(
        id="LIABILITY-CAP",
        clause="liability_cap",
        starting=Position("12 months of fees", "1 crore"),
        fallbacks=(Position("2x fees", "2 crore"),),
        dealbreaker=Position("above 5 crore", "5 crore"),
        priority=MANDATORY,
        comparator="max_amount",
    )
    r = resolve_position(cap, "Rs 80,00,000")
    check("max_amount: 80L under 1Cr → STARTING", r.status == STARTING)
    r = resolve_position(cap, "Rs 1,50,00,000")
    check("max_amount: 1.5Cr under 2Cr → FALLBACK", r.status == FALLBACK)
    r = resolve_position(cap, "Rs 10,00,00,000")
    check("max_amount: 10Cr above dealbreaker → NOT_ACCEPTABLE", r.status == NOT_ACCEPTABLE)

    # resolve_all
    playbook = PositionPlaybook(
        id="test-pb",
        version="1",
        rules=(survival, gov_law),
    )
    extracted = {"survival_period": "three years", "governing_law": "India"}
    results = resolve_all(playbook, extracted)
    check("resolve_all: returns one result per rule", len(results) == 2)
    check("resolve_all: survival → FALLBACK", results[0].status == FALLBACK)
    check("resolve_all: gov_law → STARTING", results[1].status == STARTING)

    # priority preserved
    check("priority preserved on result", results[0].priority == MANDATORY)
    check("priority RECOMMENDED on gov_law", results[1].priority == RECOMMENDED)

    # confidence scores (Fuzzy Triage, arXiv 2603.07390)
    r = resolve_position(survival, "five years")
    check("confidence: exact starting match = 1.0", r.confidence == 1.0)
    r = resolve_position(survival, None)
    check("confidence: no value = 0.0", r.confidence == 0.0)
    r = resolve_position(survival, "forever and ever")
    check("confidence: unreadable = 0.0", r.confidence == 0.0)
    r = resolve_position(cap, "Rs 10,00,00,000")
    check("confidence: NOT_ACCEPTABLE has numeric confidence", 0.0 <= r.confidence <= 1.0)

    # vocabulary: no forbidden legal verdict words
    all_results = [
        resolve_position(survival, v)
        for v in ("five years", "three years", "six months", None, "forever")
    ]
    banned = ("violation", "breach", "unenforceable", "illegal", "defect")
    hits = [w for r in all_results for w in banned if w in f"{r.status} {r.detail}".lower()]
    check("no legal verdict words in output", not hits)

    print(f"\n{passed + failed} tests, {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    _self_test()
