"""Typed objects where every property carries where it came from and when it was true.

Ring 1. PLAN_19 G1.1, built to `docs/plan19/decisions/M10_ONTOLOGY.md` and **not** to
PLAN_19 `03_ARCHITECTURE.md` §2 — the doubt pass found §2 naming four types that do not
exist. That is recorded in the decision; the short version:

    §2 said                                 reality
    valid: Interval (checker/interval.py)   that module is STATISTICS (wilson, mcnemar)
    an Interval type exists somewhere       none anywhere; both Interval* names are
                                            exception classes in unrelated modules
    source: provenance.Source               ABSENT. The real type is SourceRecord, and
                                            none of the three field names matched
    Unknown is a type                       no such type; three UNKNOWN *strings* exist
                                            with three different values

## The one idea

Gotham's load-bearing rule (PLAN_19 01 §1.1) is not the globe: it is that every fact on
screen carries where it came from, who may see it, and when it was true. `Observed`
below is that rule as a type. A property that cannot say those three things cannot be
stored.

## Why `SourceRef` is not a new shape

It IS `provenance.SourceRecord`. §2's own Rule 1 requires `LINK_TYPES` to come from
`entity_graph.Rel` *"so the entity graph and the ontology cannot diverge"* — the same
argument applies with more force to provenance, which every claim in this product rests
on. A renamed second source shape would be two notions of truth about origin.

Reusing it also keeps `official` and `accessibility`, which §2's three-field sketch
dropped. `accessibility` is what `feeds/` uses to tell *"the source said nothing"* from
*"the source did not answer"*, and losing it here would have re-created that hole.

## Why `Unknown` is a type and not a fourth string

`None` and `0` are both real answers in this domain — a company can have `0` charges,
and `None` is what a missing key returns. A sentinel that is neither is the only way
`Observed.value` can say *"we looked and do not know"* without colliding with an answer.

It is deliberately NOT offered as a replacement for `assessment.UNKNOWN` (`"UNKNOWN"`),
`entail_role.UNKNOWN` (`"unknown"`) or `matrix_view.UNKNOWN` (`""`). Those are local
display values with three different strings; unifying them is a separate change with its
own blast radius, and is recorded as open rather than done here.

## The failure family every guard below is aimed at

Four defects in two days (`docs/research/RED_TEAM_OPERATION_STORE_2026_09_25.md`,
`RED_TEAM_INSTRUMENT_REGISTRY_2026_09_26.md`): a `hasattr` swallowing a missing API, a
`.get(default)` turning missing into plausible, a `source` check that tested
non-emptiness instead of meaning, a fragment check that did the same.

> **A guard that tests for PRESENCE is not a guard that tests for CONTENT.**

So: `value` refuses `None`; `evidence` must be a `provenance.STATES` member, not a free
string; `licence` must be non-empty, because an empty frozenset READS as "no
restrictions" and MEANS "nobody recorded any", and PLAN_08's Axis D exists because those
are opposite facts; and `Individual`'s lack of person data is proved by a dataclass-field
scan, because a comment saying so is not a test.

## What this module does not do

No store, no persistence, no `as_of` query (move 11). No rollup and no evidence state of
its own — §2 Rule 3 puts every rollup in `derivation.py` with its witness. It decides
nothing about law.
"""
from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import date, datetime
from typing import Generic, TypeVar

from checker.entity_graph import Rel
from checker.provenance import STATES, SourceRecord

__all__ = ["Unknown", "UNKNOWN", "Validity", "Observed", "SourceRef",
           "Company", "Individual", "Instrument", "Provision", "Obligation",
           "Document", "Matter", "Judgment",
           "OBJECT_TYPES", "LINK_TYPES"]

# The provenance record IS the source reference. Not a renamed copy of it.
SourceRef = SourceRecord

T = TypeVar("T")


class Unknown:
    """"We looked and do not know" — distinct from `None` and from any real value.

    A singleton. `bool(UNKNOWN)` is False so that `if value:` cannot silently treat it
    as present, but it is NOT equal to `None`, `0`, `""` or `False`, so a caller that
    compares rather than truth-tests gets the right answer.
    """

    _instance: Unknown | None = None

    def __new__(cls) -> Unknown:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __bool__(self) -> bool:
        return False

    def __repr__(self) -> str:
        return "UNKNOWN"


UNKNOWN = Unknown()


@dataclass(frozen=True)
class Validity:
    """When a value was true in the world. NOT transaction time — that is `known_at`.

    `effective_to is None` means "still in force so far as we know", which is a
    statement about our knowledge and not about the world.

    The semantics are `prescribed_thresholds.Threshold`'s, deliberately and exactly:
    inclusive at both ends. A test asserts the two agree across a grid of dates, because
    two containment rules differing by one day at a boundary is how a point-in-time
    answer goes quietly wrong -- and `docs/TEMPORAL_PROOF.md` exists because this
    repository has already paid for boundary behaviour once.

    This type is NOT in `checker/interval.py`. That module is statistics; putting a date
    type there because the word matches would make the next reader's grep lie.
    """

    effective_from: date
    effective_to: date | None = None

    def __post_init__(self) -> None:
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError(f"validity ends ({self.effective_to}) before it begins "
                             f"({self.effective_from})")

    def covers(self, as_of: date) -> bool:
        if as_of < self.effective_from:
            return False
        return self.effective_to is None or as_of <= self.effective_to


@dataclass(frozen=True)
class Observed(Generic[T]):
    """One property of one object, with its provenance, its validity and its licence.

    Every field is required. An `Observed` that cannot say where a value came from, when
    it was true, how well it is known and what may be done with it is not an observation
    -- it is an assertion with extra steps.
    """

    value: T | Unknown
    source: SourceRef
    valid: Validity
    known_at: datetime          # transaction time: when WE recorded it
    evidence: str               # a provenance.STATES member
    licence: frozenset[str]     # PLAN_08 Axis D: rights actually held for this value

    def __post_init__(self) -> None:
        # PRESENCE vs CONTENT, guard 1. `None` is what a missing key returns, so
        # accepting it as "unknown" would make an absent field indistinguishable from a
        # recorded finding of ignorance. UNKNOWN says the second out loud.
        if self.value is None:
            raise ValueError("value is None: use UNKNOWN to record 'we looked and do "
                             "not know'. None is what a missing key returns, and the "
                             "two must not be the same answer")
        # Guard 2. A free-text evidence word is an evidence word nobody validated.
        if self.evidence not in STATES:
            raise ValueError(f"{self.evidence!r} is not a provenance state; one of {STATES}")
        # Guard 3. Empty READS as "no restrictions" and MEANS "nobody recorded any".
        # PLAN_08 Axis D exists because those are opposite facts.
        if not self.licence:
            raise ValueError("licence is empty: an empty set reads as 'no restrictions' "
                             "and means 'nobody recorded any'. Record the rights held, "
                             "or LICENCE_UNVERIFIED")
        if not isinstance(self.valid, Validity):
            raise ValueError("valid must be a Validity -- a bare date cannot say when a "
                             "value stopped being true")

    @property
    def known(self) -> bool:
        """Whether a real value was observed, as opposed to a recorded ignorance."""
        return not isinstance(self.value, Unknown)


# --- objects ------------------------------------------------------------------------
# Each is a HANDLE plus its observed properties. None carries a bare attribute, because
# a bare attribute has no provenance and no validity and is exactly what this module
# exists to prevent.

@dataclass(frozen=True)
class Company:
    entity_id: str
    properties: tuple[tuple[str, Observed], ...] = ()


@dataclass(frozen=True)
class Individual:
    """A HANDLE, never a person.

    It carries an opaque id and nothing else. `entity_graph`'s docstring already holds
    this line -- *"Entities are opaque ids with a kind ... This module stores no names,
    addresses, DINs or other PII"* -- and the mapping from handle to person lives in the
    tenant's Vault under row-level security (PLAN_18 §2.8), never here.

    Proved by a dataclass-field scan in `_test()`, not by this docstring.
    """

    entity_id: str
    properties: tuple[tuple[str, Observed], ...] = ()


@dataclass(frozen=True)
class Instrument:
    instrument_id: str
    properties: tuple[tuple[str, Observed], ...] = ()


@dataclass(frozen=True)
class Provision:
    ref: str
    properties: tuple[tuple[str, Observed], ...] = ()


@dataclass(frozen=True)
class Obligation:
    obligation_id: str
    properties: tuple[tuple[str, Observed], ...] = ()


@dataclass(frozen=True)
class Document:
    document_id: str
    properties: tuple[tuple[str, Observed], ...] = ()


@dataclass(frozen=True)
class Matter:
    matter_id: str
    properties: tuple[tuple[str, Observed], ...] = ()


@dataclass(frozen=True)
class Judgment:
    """Declared for G5 (the citator). Nothing constructs one yet.

    G5 is [BLOCKED] on counsel's answer about the Supreme Court corpus's CC-BY grant
    (PLAN_19 02 §5), so the type name exists and the machinery does not.
    """

    citation: str
    properties: tuple[tuple[str, Observed], ...] = ()


OBJECT_TYPES: tuple[str, ...] = ("Company", "Individual", "Instrument", "Provision",
                                 "Obligation", "Document", "Matter", "Judgment",
                                 "Observation")

# Built FROM entity_graph.Rel, never restated, so the entity graph and the ontology
# cannot diverge (§2 Rule 1). The additions are ontology-level edges the graph does not
# model: they relate instruments, provisions and judgments rather than entities.
_ONTOLOGY_ONLY_LINKS: tuple[str, ...] = ("AMENDS", "CITES", "TREATS", "CONCERNS",
                                         "EVIDENCES")
LINK_TYPES: tuple[str, ...] = tuple(r.name for r in Rel) + _ONTOLOGY_ONLY_LINKS


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    print("ontology")

    NOW = datetime(2026, 9, 26, 12, 0, 0)
    SRC = SourceRef(source_id="TEST", source_title="t", source_url="https://x/y",
                    official=True, accessibility="ACCESSIBLE", retrieved_on="2026-09-26")
    V = Validity(effective_from=date(2025, 12, 1))

    def obs(**kw):
        base = dict(value=1, source=SRC, valid=V, known_at=NOW,
                    evidence="CORROBORATED", licence=frozenset({"SERVE"}))
        return Observed(**{**base, **kw})

    # ---- guard 1: None is not "unknown" -----------------------------------------
    try:
        obs(value=None)
        check(False, "None was accepted as a value")
    except ValueError as e:
        check("use UNKNOWN" in str(e),
              "None is refused: a missing key and a recorded ignorance are different answers")
    check(obs(value=UNKNOWN).known is False and obs(value=0).known is True,
          "UNKNOWN is not known; 0 IS -- a company can genuinely have 0 charges")
    check(UNKNOWN is not None and UNKNOWN != 0 and UNKNOWN != "" and UNKNOWN is Unknown(),
          "UNKNOWN is a singleton distinct from None, 0 and the empty string")
    check(bool(UNKNOWN) is False,
          "...and falsy, so `if value:` cannot silently treat it as present")

    # ---- guard 2: evidence is validated, not free text ---------------------------
    try:
        obs(evidence="PROBABLY_FINE")
        check(False, "a free-text evidence word was accepted")
    except ValueError as e:
        check("not a provenance state" in str(e),
              "evidence must be a provenance.STATES member -- an unvalidated evidence "
              "word is one nobody can rely on")
    check(all(obs(evidence=s).evidence == s for s in STATES),
          f"every real provenance state is accepted ({len(STATES)} checked)")

    # ---- guard 3: an empty licence is not "no restrictions" -----------------------
    try:
        obs(licence=frozenset())
        check(False, "an empty licence set was accepted")
    except ValueError as e:
        check("nobody recorded any" in str(e),
              "an empty licence is refused: it READS as no restrictions and MEANS "
              "nobody recorded any (PLAN_08 Axis D)")

    try:
        obs(valid=date(2025, 12, 1))
        check(False, "a bare date was accepted as validity")
    except ValueError:
        check(True, "a bare date is not a Validity -- it cannot say when a value stopped "
                    "being true")

    # ---- guard 4: Individual carries no person data, PROVED not asserted ----------
    BANNED = ("name", "din", "pan", "address", "email", "phone", "dob", "aadhaar",
              "father", "nationality", "passport")
    offenders = [f.name for f in fields(Individual)
                 if any(b in f.name.lower() for b in BANNED)]
    check(not offenders,
          f"Individual carries no person-level field, by a FIELD SCAN not a comment "
          f"({[f.name for f in fields(Individual)]})")
    check([f.name for f in fields(Individual)] == ["entity_id", "properties"],
          "...and its whole shape is a handle plus observed properties")

    # ---- Validity matches Threshold EXACTLY, across a grid ------------------------
    # Compared against a REAL Threshold, calling ITS covers(). A first version of this
    # check recomputed Threshold's rule inline, which meant it could not catch the two
    # drifting apart -- a test that reimplements the thing it is comparing against is
    # testing itself. The live threshold table supplies the object, so if
    # Threshold.covers ever changes, this goes red.
    from checker.prescribed_thresholds import all_thresholds
    real = next(t for t in all_thresholds() if t.effective_to is None)
    bounded = next((t for t in all_thresholds() if t.effective_to is not None), None)
    grid = [date(2020, 1, 1), date(2022, 9, 14), date(2022, 9, 15), date(2025, 11, 30),
            date(2025, 12, 1), date(2026, 6, 30), date(2027, 1, 1)]
    disagree = []
    for t in [x for x in (real, bounded) if x is not None]:
        v = Validity(t.effective_from, t.effective_to)
        for d in grid:
            if v.covers(d) != t.covers(d):
                disagree.append((t.key, d, v.covers(d), t.covers(d)))
    check(not disagree,
          f"Validity.covers agrees with a REAL Threshold.covers on every grid date "
          f"({len(grid) * 2} comparisons, open-ended and bounded)")
    check(bounded is not None,
          "...and a bounded threshold was available, so the effective_to branch was "
          "actually exercised rather than skipped")
    try:
        Validity(date(2026, 1, 1), date(2025, 1, 1))
        check(False, "a validity ending before it begins was accepted")
    except ValueError:
        check(True, "a validity that ends before it begins is refused")

    # ---- the ontology cannot diverge from the entity graph ------------------------
    check(all(r.name in LINK_TYPES for r in Rel),
          f"every entity_graph.Rel member is a LINK_TYPE ({len(list(Rel))} of them)")
    check(len(LINK_TYPES) == len(list(Rel)) + len(_ONTOLOGY_ONLY_LINKS)
          and len(set(LINK_TYPES)) == len(LINK_TYPES),
          "LINK_TYPES is Rel plus the ontology-only edges, with no duplicates")
    check("Judgment" in OBJECT_TYPES,
          "Judgment is declared for G5, which is BLOCKED on counsel -- the name exists, "
          "the machinery does not")

    # ---- SourceRef is provenance's own type, not a copy ---------------------------
    check(SourceRef is SourceRecord,
          "SourceRef IS provenance.SourceRecord -- no renamed second shape to diverge")
    check(hasattr(SRC, "accessibility") and hasattr(SRC, "official"),
          "...so `accessibility` and `official` survive, which PLAN_19 §2's three-field "
          "sketch would have dropped")

    # ---- the ring boundary ---------------------------------------------------------
    from checker import rings
    check(rings.ring_of("checker.ontology") == rings.RING_1, "this module is Ring 1")
    check(not [v for v in rings.violations() if "ontology" in v],
          "...and introduces no ring violation")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
