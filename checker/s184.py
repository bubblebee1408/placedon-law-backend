"""s.184 — disclosure of interest by a director. Pure entity-graph; no threshold.

Grounded in the corpus text of s.184 (read, not recalled). Two limbs:

  s.184(1) — every director discloses his concern/interest in other companies,
             bodies corporate and firms (the annual Form MBP-1 disclosure), at the
             first Board meeting of each financial year and on any change.
  s.184(2) — a director concerned or interested in a specific contract/arrangement
             shall disclose the nature of his interest at the Board meeting and
             SHALL NOT PARTICIPATE. The interest that triggers this is, precisely:
               (a) a body corporate in which the director (alone or with other
                   directors) holds MORE THAN 2% shareholding, or is a promoter,
                   manager or CEO; or
               (b) a firm or other entity in which the director is a partner,
                   owner or member.

## A distinction the text forces

Being a DIRECTOR of the counterparty is NOT, by itself, a s.184(2) trigger — the
Act lists >2% shareholding / promoter / manager / CEO / partner / owner / member,
not directorship. (Directorship drives s.185/s.188, not s.184(2).) So this decider
does not treat a bare directorship as interest — grounding in the text, not the
intuition, keeps the limbs honest.

## What is modelled, and what abstains

Modelled from the graph: >2% shareholding (a), partner/member of a firm (b). NOT
modelled: promoter / manager / CEO roles (no such edges yet). So a POSITIVE interest
is found from the modelled limbs; a NEGATIVE ("not interested") is returned only
when the modelled limbs are provably absent AND the caller vouches the unmodelled
roles do not apply. Otherwise UNKNOWN.
"""
from __future__ import annotations

from dataclasses import dataclass

from checker.entity_graph import Answer, EntityGraph, Rel

INTERESTED_MUST_DISCLOSE = "INTERESTED_MUST_DISCLOSE"
NOT_INTERESTED = "NOT_INTERESTED"
CANNOT_DETERMINE = "CANNOT_DETERMINE"

PROVISION = "Companies Act 2013, s.184"
_SHAREHOLDING_TRIGGER = 2.0     # s.184(2)(a): "more than two per cent"


@dataclass(frozen=True)
class Determination:
    status: str
    reason: str
    conditions: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()

    @property
    def needs_attention(self) -> bool:
        return self.status in (INTERESTED_MUST_DISCLOSE, CANNOT_DETERMINE)


def is_interested(director: str, counterparty: str, graph: EntityGraph,
                  *, assume_no_unmodelled_roles: bool = False) -> Answer:
    """s.184(2) interest test on the graph. Tri-state.

    YES from a modelled limb (>2% shareholding, or partner/member of the entity).
    NO only when those are provably absent AND the caller vouches the unmodelled
    promoter/manager/CEO roles do not apply. Otherwise UNKNOWN.
    """
    # (a) more than two per cent shareholding in the counterparty body corporate
    pct = graph.shareholding(director, counterparty)
    if pct is not None and pct > _SHAREHOLDING_TRIGGER:
        return Answer.YES
    # (b) partner / member of the counterparty firm or entity
    if graph.holds(director, Rel.PARTNER_IN, counterparty) is Answer.YES:
        return Answer.YES
    if graph.holds(director, Rel.MEMBER_OF, counterparty) is Answer.YES:
        return Answer.YES

    # No modelled limb triggered. A NEGATIVE needs every modelled limb provably
    # ruled out AND a vouch on the unmodelled roles (promoter/manager/CEO).
    shareholding_ruled_out = pct is not None and pct <= _SHAREHOLDING_TRIGGER
    modelled_absent = (shareholding_ruled_out
                       and graph.holds(director, Rel.PARTNER_IN, counterparty) is Answer.NO
                       and graph.holds(director, Rel.MEMBER_OF, counterparty) is Answer.NO)
    if modelled_absent and assume_no_unmodelled_roles:
        return Answer.NO
    return Answer.UNKNOWN


def assess(director: str, counterparty: str, graph: EntityGraph,
           *, assume_no_unmodelled_roles: bool = False) -> Determination:
    """Whether s.184(2) requires this director to disclose and abstain on a
    contract with `counterparty`."""
    interest = is_interested(director, counterparty, graph,
                             assume_no_unmodelled_roles=assume_no_unmodelled_roles)
    if interest is Answer.YES:
        return Determination(INTERESTED_MUST_DISCLOSE,
                             "the director is concerned/interested in a contract with this "
                             "counterparty (s.184(2)): the director must disclose the nature "
                             "of the interest at the Board meeting and must not participate",
                             conditions=("disclosure of the nature of interest at the Board "
                                         "meeting (s.184(2))",
                                         "the interested director does not participate or vote"))
    if interest is Answer.NO:
        return Determination(NOT_INTERESTED,
                             "the director is not concerned/interested in a contract with this "
                             "counterparty under the modelled s.184(2) limbs")
    return Determination(CANNOT_DETERMINE,
                         "cannot establish the director's interest (s.184(2)): the modelled "
                         "limbs (>2% shareholding, partner/member) did not trigger and the "
                         "unmodelled roles (promoter/manager/CEO) are not ruled out",
                         missing=("the director's shareholding in and partner/member status "
                                  "with the counterparty, and whether they are its promoter/"
                                  "manager/CEO",))


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

    print("s184")
    from checker.entity_graph import Entity, Kind, Relationship

    def base():
        return (EntityGraph()
                .with_entity(Entity("DIR", Kind.INDIVIDUAL))
                .with_entity(Entity("BODYCO", Kind.COMPANY))
                .with_entity(Entity("FIRM", Kind.COMPANY)))

    # ── (a) >2% shareholding triggers interest ──────────────────────────────
    g = base().with_relationship(
        Relationship("DIR", Rel.HOLDS_SHARES_IN, "BODYCO", percent=3.0))
    d = assess("DIR", "BODYCO", g)
    check(d.status == INTERESTED_MUST_DISCLOSE,
          f">2% shareholding triggers disclose-and-abstain ({d.status})")
    check(any("not participate" in c for c in d.conditions),
          "...and the conditions include non-participation")

    # exactly 2% does NOT trigger (the Act says MORE than two per cent)
    g2 = base().with_relationship(
        Relationship("DIR", Rel.HOLDS_SHARES_IN, "BODYCO", percent=2.0))
    # 2% alone, with nothing else known, is UNKNOWN (partner/member unknown)
    check(assess("DIR", "BODYCO", g2).status == CANNOT_DETERMINE,
          "exactly 2% shareholding does not trigger; other limbs unknown -> CANNOT_DETERMINE")

    # ── (b) partner/member of a firm triggers interest ──────────────────────
    g3 = base().with_relationship(Relationship("DIR", Rel.PARTNER_IN, "FIRM"))
    check(assess("DIR", "FIRM", g3).status == INTERESTED_MUST_DISCLOSE,
          "being a partner in the counterparty firm triggers interest")

    # ── a bare directorship of the counterparty is NOT a s.184(2) trigger ───
    g4 = base().with_relationship(Relationship("DIR", Rel.DIRECTOR_OF, "BODYCO"))
    check(assess("DIR", "BODYCO", g4).status == CANNOT_DETERMINE,
          "a bare directorship of the counterparty is NOT s.184(2) interest by itself")

    # ── absence is CANNOT_DETERMINE, not NOT_INTERESTED ─────────────────────
    check(assess("DIR", "BODYCO", base()).status == CANNOT_DETERMINE,
          "with nothing known, interest is CANNOT_DETERMINE, never assumed absent")

    # ── NOT_INTERESTED only when provably absent + vouched ──────────────────
    g5 = (base()
          .with_relationship(Relationship("DIR", Rel.HOLDS_SHARES_IN, "BODYCO", percent=1.0))
          .declare_complete("DIR", Rel.PARTNER_IN)
          .declare_complete("DIR", Rel.MEMBER_OF))
    d5 = assess("DIR", "BODYCO", g5, assume_no_unmodelled_roles=True)
    check(d5.status == NOT_INTERESTED,
          f"<=2% + no partner/member + vouch on roles -> NOT_INTERESTED ({d5.status})")
    # without the vouch, it stays CANNOT_DETERMINE (promoter/manager/CEO unmodelled)
    check(assess("DIR", "BODYCO", g5).status == CANNOT_DETERMINE,
          "without the vouch on unmodelled roles it stays CANNOT_DETERMINE")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
