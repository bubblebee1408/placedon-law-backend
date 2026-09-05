"""A deterministic graph of corporate entities and their relationships.

The commercially important duties — s.185 (loans to directors and their
relatives), s.186 (investment through layers), s.188 (related-party transactions)
— cannot be decided from `CompanyProfile`, which carries only boolean flags
(is_holding_company). They turn on *relationships between named entities*: who
directs whom, who is a relative of whom (s.2(77)), who controls whom (s.2(27)),
who holds how many shares. This module is that substrate — the "Corporate Entity
Graph" the plan named as the real next data structure — and nothing more yet: it
holds entities and typed, dated, directed relationships and answers questions
about them. It does NOT decide any obligation; the deciders build on it later.

## The one discipline that makes it safe: absence is not denial

A graph that answered "is X a director of Y?" with NO whenever it held no such
edge would manufacture a fact from silence — the exact failure the whole project
refuses. So existence queries are TRI-STATE: YES if an edge is present; NO ONLY
when the graph has been explicitly told the relevant edges are completely known
(a `complete(...)` assertion); otherwise UNKNOWN. "We have no record" and "it does
not exist" are different answers, and only a completeness assertion closes the gap.

## Identifiers, not identities

Entities are opaque ids with a kind (COMPANY / INDIVIDUAL). This module stores no
names, addresses, DINs or other PII — an id is a handle a caller maps to a real
entity outside this graph, keeping the substrate free of person-level data, the
same line `company_profile` holds.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class Kind(str, Enum):
    COMPANY = "COMPANY"
    INDIVIDUAL = "INDIVIDUAL"


class Rel(str, Enum):
    """Directed relationship types, each with the section that needs it."""
    DIRECTOR_OF = "DIRECTOR_OF"        # individual -> company (s.184/185/188)
    RELATIVE_OF = "RELATIVE_OF"        # individual -> individual (s.2(77), for s.185/188)
    CONTROLS = "CONTROLS"              # entity -> company: control per s.2(27) (s.2(87), s.186)
    HOLDS_SHARES_IN = "HOLDS_SHARES_IN"  # entity -> company, carries percent (s.2(87), s.188)
    PARTNER_IN = "PARTNER_IN"          # individual -> firm/LLP (s.188 related party)
    MEMBER_OF = "MEMBER_OF"            # individual -> body corporate (s.188)


class Answer(str, Enum):
    YES = "YES"
    NO = "NO"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class Entity:
    id: str
    kind: Kind

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("an entity needs a non-empty id")


@dataclass(frozen=True)
class Relationship:
    src: str
    rel: Rel
    dst: str
    as_of: date | None = None          # when it is asserted to hold; None = undated
    percent: float | None = None       # for HOLDS_SHARES_IN; None = unknown, never 0
    basis: str = ""                    # where this edge came from

    def __post_init__(self) -> None:
        if self.src == self.dst:
            raise ValueError(f"a relationship must be between two entities, not {self.src!r} to itself")
        if self.percent is not None and not (0.0 <= self.percent <= 100.0):
            raise ValueError(f"a shareholding percent must be in [0,100], got {self.percent}")


# A completeness assertion. Direction says which side is complete: OUT = "every
# edge of type `rel` FROM `entity` is known" (settles "does A relate to ?"); IN =
# "every edge of type `rel` INTO `entity` is known" (settles "are these ALL the
# directors of this company?"). It is what lets a query answer NO/complete instead
# of UNKNOWN.
class Direction(str, Enum):
    OUT = "OUT"
    IN = "IN"


@dataclass(frozen=True)
class Complete:
    entity: str
    rel: Rel
    direction: Direction = Direction.OUT


@dataclass(frozen=True)
class EntityGraph:
    entities: tuple[Entity, ...] = ()
    relationships: tuple[Relationship, ...] = ()
    completeness: tuple[Complete, ...] = ()

    # ── immutable builders (return a new graph, never mutate) ───────────────
    def with_entity(self, entity: Entity) -> "EntityGraph":
        if any(e.id == entity.id for e in self.entities):
            return self
        return EntityGraph(self.entities + (entity,), self.relationships, self.completeness)

    def with_relationship(self, rel: Relationship) -> "EntityGraph":
        # An edge implies its endpoints exist, but as UNKNOWN-kind is not allowed;
        # endpoints must be added first so a kind is never guessed.
        known = {e.id for e in self.entities}
        missing = {rel.src, rel.dst} - known
        if missing:
            raise ValueError(f"add entities before relating them; unknown: {sorted(missing)}")
        return EntityGraph(self.entities, self.relationships + (rel,), self.completeness)

    def declare_complete(self, entity: str, rel: Rel) -> "EntityGraph":
        """Assert every OUTgoing edge of `rel` from `entity` is known."""
        c = Complete(entity, rel, Direction.OUT)
        if c in self.completeness:
            return self
        return EntityGraph(self.entities, self.relationships, self.completeness + (c,))

    def declare_complete_into(self, entity: str, rel: Rel) -> "EntityGraph":
        """Assert every INcoming edge of `rel` into `entity` is known (e.g. the
        full set of directors of a company)."""
        c = Complete(entity, rel, Direction.IN)
        if c in self.completeness:
            return self
        return EntityGraph(self.entities, self.relationships, self.completeness + (c,))

    # ── queries ─────────────────────────────────────────────────────────────
    def _is_complete(self, entity: str, rel: Rel,
                     direction: Direction = Direction.OUT) -> bool:
        return Complete(entity, rel, direction) in self.completeness

    def complete_into(self, entity: str, rel: Rel) -> bool:
        """Whether the incoming edges of `rel` into `entity` are declared complete."""
        return self._is_complete(entity, rel, Direction.IN)

    def out(self, src: str, rel: Rel) -> list[Relationship]:
        """Known outgoing edges of a type. May be incomplete — see `holds`."""
        return [r for r in self.relationships if r.src == src and r.rel == rel]

    def into(self, dst: str, rel: Rel) -> list[Relationship]:
        """Known incoming edges of a type. May be incomplete — see `complete_into`."""
        return [r for r in self.relationships if r.dst == dst and r.rel == rel]

    def directors_of(self, company: str) -> list[str]:
        """The KNOWN directors of a company (may be incomplete)."""
        return [r.src for r in self.into(company, Rel.DIRECTOR_OF)]

    def controllers_of(self, company: str) -> list[str]:
        """The KNOWN entities that control a company (its holding companies)."""
        return [r.src for r in self.into(company, Rel.CONTROLS)]

    def holds(self, src: str, rel: Rel, dst: str) -> Answer:
        """Tri-state: does `src --rel--> dst` hold?

        YES if the edge is present. NO only if the graph is told `src`'s edges of
        this type are complete (so a missing edge is a real absence). Otherwise
        UNKNOWN — the honest answer to "we have no record".
        """
        if any(r.src == src and r.rel == rel and r.dst == dst for r in self.relationships):
            return Answer.YES
        # A real absence is settled by completeness on EITHER side: the source's
        # OUT edges are fully known, OR the destination's IN edges are (e.g. the
        # company's full board is known, so a name not on it is not a director).
        if (self._is_complete(src, rel, Direction.OUT)
                or self._is_complete(dst, rel, Direction.IN)):
            return Answer.NO
        return Answer.UNKNOWN

    def is_director(self, individual: str, company: str) -> Answer:
        return self.holds(individual, Rel.DIRECTOR_OF, company)

    def are_relatives(self, a: str, b: str) -> Answer:
        """s.2(77) relation. Recorded either direction counts; completeness of
        EITHER endpoint's RELATIVE_OF edges can settle a NO."""
        if any(r.rel == Rel.RELATIVE_OF and {r.src, r.dst} == {a, b}
               for r in self.relationships):
            return Answer.YES
        if self._is_complete(a, Rel.RELATIVE_OF) or self._is_complete(b, Rel.RELATIVE_OF):
            return Answer.NO
        return Answer.UNKNOWN

    def shareholding(self, holder: str, company: str) -> float | None:
        """The recorded percent, or None if unknown. Never defaults to 0 — an
        unknown holding is not a nil holding (the s.2(85)/'unknown is not zero'
        discipline, here for control tests)."""
        for r in self.out(holder, Rel.HOLDS_SHARES_IN):
            if r.dst == company:
                return r.percent
        return None

    def entity_kind(self, entity_id: str) -> Kind | None:
        for e in self.entities:
            if e.id == entity_id:
                return e.kind
        return None


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

    print("entity_graph")

    acme = Entity("ACME", Kind.COMPANY)
    p_dir = Entity("P1", Kind.INDIVIDUAL)
    p_rel = Entity("P2", Kind.INDIVIDUAL)
    hold = Entity("HOLDCO", Kind.COMPANY)

    g = (EntityGraph()
         .with_entity(acme).with_entity(p_dir).with_entity(p_rel).with_entity(hold))

    # ── immutability: builders return new graphs ────────────────────────────
    g2 = g.with_relationship(Relationship("P1", Rel.DIRECTOR_OF, "ACME", basis="Form DIR-12"))
    check(len(g.relationships) == 0 and len(g2.relationships) == 1,
          "with_relationship returns a new graph; the original is unchanged")

    # ── absence is UNKNOWN, not NO ──────────────────────────────────────────
    check(g2.is_director("P1", "ACME") is Answer.YES, "a recorded directorship is YES")
    check(g2.is_director("P2", "ACME") is Answer.UNKNOWN,
          "an unrecorded directorship is UNKNOWN, not NO")

    # ── completeness turns a missing edge into an honest NO ─────────────────
    g3 = g2.declare_complete("P2", Rel.DIRECTOR_OF)
    check(g3.is_director("P2", "ACME") is Answer.NO,
          "with P2's directorships declared complete, absence becomes NO")
    check(g3.is_director("P1", "ACME") is Answer.YES,
          "...and a present edge is still YES")

    # ── relatives: either direction, completeness of either endpoint ────────
    g4 = g2.with_relationship(Relationship("P1", Rel.RELATIVE_OF, "P2", basis="declared"))
    check(g4.are_relatives("P1", "P2") is Answer.YES, "a recorded relation is YES either way")
    check(g4.are_relatives("P2", "P1") is Answer.YES, "...symmetric on lookup")
    check(g4.are_relatives("P1", "HOLDCO") is Answer.UNKNOWN,
          "an unrecorded relation is UNKNOWN")
    g5 = g4.declare_complete("P1", Rel.RELATIVE_OF)
    check(g5.are_relatives("P1", "HOLDCO") is Answer.NO,
          "completeness of one endpoint settles a NO")

    # ── shareholding: unknown is None, never 0 ──────────────────────────────
    g6 = g2.with_relationship(
        Relationship("HOLDCO", Rel.HOLDS_SHARES_IN, "ACME", percent=60.0, basis="MGT-7"))
    check(g6.shareholding("HOLDCO", "ACME") == 60.0, "a recorded holding reads back")
    check(g6.shareholding("P1", "ACME") is None,
          "an unrecorded holding is None, never 0 (unknown is not nil)")

    # ── invariants enforced at construction ─────────────────────────────────
    try:
        Relationship("A", Rel.DIRECTOR_OF, "A")
        check(False, "a self-relationship is rejected")
    except ValueError:
        check(True, "a self-relationship is rejected")
    try:
        Relationship("H", Rel.HOLDS_SHARES_IN, "C", percent=140.0)
        check(False, "an out-of-range percent is rejected")
    except ValueError:
        check(True, "a shareholding percent outside [0,100] is rejected")
    try:
        g.with_relationship(Relationship("GHOST", Rel.DIRECTOR_OF, "ACME"))
        check(False, "relating an unknown entity is rejected")
    except ValueError:
        check(True, "an edge to an entity not in the graph is rejected (no guessed kind)")

    # ── entity kinds are stored, not inferred ───────────────────────────────
    check(g.entity_kind("ACME") is Kind.COMPANY and g.entity_kind("P1") is Kind.INDIVIDUAL,
          "entity kinds are recorded")
    check(g.entity_kind("NOBODY") is None, "an unknown entity has no kind, not a default one")

    # ── incoming queries + directional completeness ─────────────────────────
    from checker.entity_graph import Direction  # noqa: F401 (self-import for clarity)
    gd = (EntityGraph().with_entity(acme).with_entity(p_dir).with_entity(p_rel)
          .with_relationship(Relationship("P1", Rel.DIRECTOR_OF, "ACME"))
          .with_relationship(Relationship("P2", Rel.DIRECTOR_OF, "ACME")))
    check(set(gd.directors_of("ACME")) == {"P1", "P2"},
          f"directors_of lists the known directors ({sorted(gd.directors_of('ACME'))})")
    check(gd.directors_of("HOLDCO") == [], "a company with no known directors lists none")
    check(len(gd.into("ACME", Rel.DIRECTOR_OF)) == 2, "into() returns incoming edges")
    check(not gd.complete_into("ACME", Rel.DIRECTOR_OF),
          "the director list is NOT complete until declared")
    gdc = gd.declare_complete_into("ACME", Rel.DIRECTOR_OF)
    check(gdc.complete_into("ACME", Rel.DIRECTOR_OF),
          "declare_complete_into marks the incoming set complete")
    check(not gdc._is_complete("ACME", Rel.DIRECTOR_OF),
          "IN completeness does not leak into OUT completeness (they are distinct)")

    # ── no PII fields on the entity ─────────────────────────────────────────
    import dataclasses as _dc
    fields = {f.name for f in _dc.fields(Entity)}
    check(fields == {"id", "kind"},
          f"an entity is only an opaque id + kind, no person-level data ({fields})")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
