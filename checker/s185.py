"""s.185 — loans to directors etc.: is a proposed loan/guarantee/security caught?

A transaction-scoped decider, not a company-wide obligation row. Given a lending
company, a counterparty, and an entity graph, it determines whether s.185 catches
the transaction and, if so, what it requires. Grounded in the corpus text of
s.185 (read, not recalled):

  (1) ABSOLUTE PROHIBITION on a loan/guarantee/security to
      (a) a director of the company or of its holding company, or a partner or
          relative of any such director; or
      (b) a firm in which any such director or relative is a partner.
  (2) MAY lend to a person "in whom a director is interested" (Explanation:
      a private company the director is a director/member of; a body corporate
      where such directors control >=25% of voting power; a body corporate
      accustomed to act on the lending company's directions) — subject to a
      special resolution AND use for the borrower's principal business activity.
  (3) EXEMPTIONS: MD/WTD service-condition or member-approved-scheme loans; a
      company in the ordinary business of lending at the prescribed interest;
      a holding->wholly-owned-subsidiary loan; a holding-company guarantee for a
      bank loan to its subsidiary (both used for the subsidiary's principal
      business).

## The discipline: this decider abstains far more than it decides

Every branch turns on relationships that may be UNKNOWN. The five outcomes are:

  PROHIBITED                    — a (1) relationship is positively established
  PERMITTED_WITH_CONDITIONS     — a (2) interest is established; names the
                                  special-resolution + principal-business conditions
  EXEMPT                        — a (3) exemption is positively established
  NOT_CAUGHT                    — every (1)/(2) relationship is known-absent
                                  (requires completeness); a real, earned negative
  CANNOT_DETERMINE              — some relationship is UNKNOWN; names what to supply

A NOT_CAUGHT is only returned when the graph can PROVE the counterparty is in none
of the caught classes — which needs completeness assertions. Absent those, the
honest answer is CANNOT_DETERMINE with the missing facts named. This decider never
says "fine" from silence.

It does not compute the penalty (s.185(4)); it decides applicability and the gate.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from checker.entity_graph import Answer, EntityGraph, Rel

PROHIBITED = "PROHIBITED"
PERMITTED_WITH_CONDITIONS = "PERMITTED_WITH_CONDITIONS"
EXEMPT = "EXEMPT"
NOT_CAUGHT = "NOT_CAUGHT"
CANNOT_DETERMINE = "CANNOT_DETERMINE"

PROVISION = "Companies Act 2013, s.185"


@dataclass(frozen=True)
class LoanFacts:
    """What is known about the transaction beyond the graph relationships."""
    company: str
    counterparty: str
    # s.185(2) conditions, each tri-valued (None = unknown):
    special_resolution_passed: bool | None = None
    used_for_principal_business: bool | None = None
    # s.185(3) exemption facts, each tri-valued (None = unknown):
    counterparty_is_wholly_owned_subsidiary: bool | None = None
    lender_in_ordinary_business_of_lending: bool | None = None


@dataclass(frozen=True)
class Determination:
    status: str
    reason: str
    conditions: tuple[str, ...] = ()      # what must be true for a conditional permit
    missing: tuple[str, ...] = ()          # facts that would move CANNOT_DETERMINE forward
    caught_by: str = ""                    # the limb that catches it, when caught

    @property
    def needs_attention(self) -> bool:
        return self.status in (PROHIBITED, PERMITTED_WITH_CONDITIONS, CANNOT_DETERMINE)


def _such_directors(company: str, graph: EntityGraph) -> tuple[list[str], bool]:
    """The directors 'of the company or of its holding company' (s.185(1)(a)),
    and whether that set can be treated as COMPLETE.

    Complete iff the company's directors are complete AND, for every known holding
    company, its directors are complete AND the set of holding companies is
    complete. Anything unknown makes the set potentially larger than we can see.
    """
    directors = list(graph.directors_of(company))
    holdcos = graph.controllers_of(company)
    for h in holdcos:
        directors.extend(graph.directors_of(h))
    complete = (graph.complete_into(company, Rel.DIRECTOR_OF)
                and graph.complete_into(company, Rel.CONTROLS)
                and all(graph.complete_into(h, Rel.DIRECTOR_OF) for h in holdcos))
    return list(dict.fromkeys(directors)), complete


def assess(facts: LoanFacts, graph: EntityGraph) -> Determination:
    cp = facts.counterparty
    company = facts.company
    directors, directors_complete = _such_directors(company, graph)

    # ── (3) exemptions first: they override (1) and (2), but only when POSITIVELY
    # established. An unknown exemption fact is not an exemption. ─────────────
    if facts.counterparty_is_wholly_owned_subsidiary is True:
        return Determination(EXEMPT,
                             "counterparty is a wholly-owned subsidiary of the lender "
                             "(s.185(3)(c)), subject to principal-business use",
                             conditions=("the loan is used for the subsidiary's "
                                         "principal business activities",),
                             caught_by="s.185(3)(c)")
    if facts.lender_in_ordinary_business_of_lending is True:
        return Determination(EXEMPT,
                             "the lender is in the ordinary business of lending "
                             "(s.185(3)(b)), subject to the prescribed interest floor",
                             conditions=("interest is charged at not less than the "
                                         "prevailing Government-security yield (s.185(3)(b))",),
                             caught_by="s.185(3)(b)")

    # ── (1) absolute prohibition ────────────────────────────────────────────
    # (1)(a) the counterparty IS such a director.
    if any(graph.holds(cp, Rel.DIRECTOR_OF, d_co) is Answer.YES
           for d_co in ([company] + graph.controllers_of(company))):
        return Determination(PROHIBITED,
                             "counterparty is a director of the company or its holding "
                             "company (s.185(1)(a))", caught_by="s.185(1)(a)")

    # (1)(a) the counterparty is a RELATIVE of such a director.
    rel_hits = [d for d in directors if graph.are_relatives(cp, d) is Answer.YES]
    if rel_hits:
        return Determination(PROHIBITED,
                             "counterparty is a relative of a director of the company "
                             "or its holding company (s.185(1)(a))", caught_by="s.185(1)(a)")

    # (1)(a) the counterparty is a PARTNER of such a director; (1)(b) a firm in
    # which such a director or relative is a partner.
    if any(graph.holds(cp, Rel.PARTNER_IN, d) is Answer.YES for d in directors):
        return Determination(PROHIBITED,
                             "counterparty is a partner of such a director (s.185(1)(a))",
                             caught_by="s.185(1)(a)")
    if any(graph.holds(d, Rel.PARTNER_IN, cp) is Answer.YES for d in directors):
        return Determination(PROHIBITED,
                             "counterparty is a firm in which such a director is a partner "
                             "(s.185(1)(b))", caught_by="s.185(1)(b)")

    # ── (2) a person in whom a director is interested ───────────────────────
    # Established here via a director being a MEMBER of the counterparty (a private
    # company) or the counterparty being controlled >=25% by such directors. The
    # graph supports MEMBER_OF and HOLDS_SHARES_IN percentages.
    interested = (any(graph.holds(d, Rel.MEMBER_OF, cp) is Answer.YES for d in directors)
                  or _voting_control_ge_25(directors, cp, graph) is Answer.YES)
    if interested:
        conds = ("a special resolution is passed with full particulars disclosed "
                 "in the explanatory statement (s.185(2)(a))",
                 "the loan is used for the borrower's principal business activities "
                 "(s.185(2)(b))")
        satisfied = (facts.special_resolution_passed is True
                     and facts.used_for_principal_business is True)
        if satisfied:
            return Determination(PERMITTED_WITH_CONDITIONS,
                                 "counterparty is a person in whom a director is interested "
                                 "(s.185(2)); the two conditions are recorded as met",
                                 conditions=conds, caught_by="s.185(2)")
        missing = []
        if facts.special_resolution_passed is not True:
            missing.append("whether the special resolution under s.185(2)(a) was passed")
        if facts.used_for_principal_business is not True:
            missing.append("whether the loan is for the borrower's principal business")
        return Determination(CANNOT_DETERMINE,
                             "counterparty is a person in whom a director is interested "
                             "(s.185(2)); the conditions are not established",
                             conditions=conds, missing=tuple(missing), caught_by="s.185(2)")

    # ── nothing caught. Only a real NEGATIVE if we can prove it. ────────────
    if not _can_rule_out(cp, directors, directors_complete, graph):
        return Determination(CANNOT_DETERMINE,
                             "no caught relationship is established, but the graph cannot "
                             "prove the counterparty is in none of the s.185 classes",
                             missing=_what_would_settle(cp, company, directors,
                                                        directors_complete, graph))
    return Determination(NOT_CAUGHT,
                         "the counterparty is a known non-director, non-relative, "
                         "non-partner, non-interested party — s.185 does not catch it")


def _voting_control_ge_25(directors: list[str], cp: str, graph: EntityGraph) -> Answer:
    """s.185 Explanation (b): >=25% of total voting power controlled by such
    directors together. Uses recorded shareholding as a proxy for voting power.
    UNKNOWN if any director's holding in cp is unrecorded (unknown is not zero)."""
    total = 0.0
    any_unknown = False
    for d in directors:
        pct = graph.shareholding(d, cp)
        if pct is None:
            any_unknown = True
        else:
            total += pct
    if total >= 25.0:
        return Answer.YES
    return Answer.UNKNOWN if any_unknown else Answer.NO


def _can_rule_out(cp: str, directors: list[str], directors_complete: bool,
                  graph: EntityGraph) -> bool:
    """True only if the counterparty can be PROVEN outside every caught class."""
    if not directors_complete:
        return False                       # an unknown director could catch it
    # cp is not a director of company/holdco: needs cp's directorships complete.
    if not graph._is_complete(cp, Rel.DIRECTOR_OF):
        return False
    # cp is not a relative/partner of any known director, nor a firm with such a
    # partner: needs cp's relative/partner edges complete, and each director's.
    if not (graph._is_complete(cp, Rel.RELATIVE_OF)
            and graph._is_complete(cp, Rel.PARTNER_IN)
            and graph._is_complete(cp, Rel.MEMBER_OF)):
        return False
    for d in directors:
        if not (graph._is_complete(d, Rel.PARTNER_IN)
                and graph._is_complete(d, Rel.MEMBER_OF)
                and graph.shareholding(d, cp) is not None):
            return False
    return True


def _what_would_settle(cp: str, company: str, directors: list[str],
                       directors_complete: bool, graph: EntityGraph) -> tuple[str, ...]:
    out: list[str] = []
    if not directors_complete:
        out.append(f"the complete list of directors of {company} and its holding companies")
    if not graph._is_complete(cp, Rel.DIRECTOR_OF):
        out.append(f"whether {cp} is itself a director (declare complete to settle)")
    if any(graph.shareholding(d, cp) is None for d in directors):
        out.append(f"each director's shareholding in {cp} (for the 25% control test)")
    if not out:
        out.append("completeness of the counterparty's relative/partner/member edges")
    return tuple(out)


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

    print("s185")
    from checker.entity_graph import Entity, Kind, Relationship

    def base():
        return (EntityGraph()
                .with_entity(Entity("CO", Kind.COMPANY))
                .with_entity(Entity("DIR", Kind.INDIVIDUAL))
                .with_entity(Entity("REL", Kind.INDIVIDUAL))
                .with_entity(Entity("FIRM", Kind.COMPANY))
                .with_entity(Entity("OUT", Kind.INDIVIDUAL))
                .with_relationship(Relationship("DIR", Rel.DIRECTOR_OF, "CO")))

    # ── (1)(a): a loan to a director is PROHIBITED ──────────────────────────
    d = assess(LoanFacts("CO", "DIR"), base())
    check(d.status == PROHIBITED and d.caught_by == "s.185(1)(a)",
          f"a loan to a director is PROHIBITED ({d.status})")

    # ── (1)(a): a loan to a director's relative is PROHIBITED ───────────────
    g = base().with_relationship(Relationship("REL", Rel.RELATIVE_OF, "DIR"))
    d2 = assess(LoanFacts("CO", "REL"), g)
    check(d2.status == PROHIBITED, "a loan to a director's relative is PROHIBITED")

    # ── (1)(b): a loan to a firm in which a director is a partner ───────────
    g3 = base().with_relationship(Relationship("DIR", Rel.PARTNER_IN, "FIRM"))
    d3 = assess(LoanFacts("CO", "FIRM"), g3)
    check(d3.status == PROHIBITED and d3.caught_by == "s.185(1)(b)",
          f"a loan to a director's firm is PROHIBITED ({d3.caught_by})")

    # ── (2): interested person via >=25% control -> conditional ─────────────
    g4 = (base().with_entity(Entity("PVT", Kind.COMPANY))
          .with_relationship(Relationship("DIR", Rel.HOLDS_SHARES_IN, "PVT", percent=30.0)))
    d4 = assess(LoanFacts("CO", "PVT"), g4)
    check(d4.status == CANNOT_DETERMINE and d4.caught_by == "s.185(2)",
          f"an interested-person loan without conditions is CANNOT_DETERMINE ({d4.status})")
    check(any("special resolution" in m for m in d4.missing),
          "...and names the special-resolution condition as missing")
    d4b = assess(LoanFacts("CO", "PVT", special_resolution_passed=True,
                           used_for_principal_business=True), g4)
    check(d4b.status == PERMITTED_WITH_CONDITIONS,
          f"...and PERMITTED_WITH_CONDITIONS once both conditions are met ({d4b.status})")

    # ── (3)(c): a loan to a wholly-owned subsidiary is EXEMPT ───────────────
    d5 = assess(LoanFacts("CO", "OUT", counterparty_is_wholly_owned_subsidiary=True), base())
    check(d5.status == EXEMPT and d5.caught_by == "s.185(3)(c)",
          f"a loan to a WOS is EXEMPT ({d5.status})")

    # ── absence is CANNOT_DETERMINE, not NOT_CAUGHT ─────────────────────────
    d6 = assess(LoanFacts("CO", "OUT"), base())
    check(d6.status == CANNOT_DETERMINE,
          f"an unrelated party with incomplete graph is CANNOT_DETERMINE ({d6.status})")
    check(bool(d6.missing), "...and names what would settle it")

    # ── NOT_CAUGHT only when everything is provably absent ──────────────────
    g7 = (base()
          .declare_complete_into("CO", Rel.DIRECTOR_OF)
          .declare_complete_into("CO", Rel.CONTROLS)
          .declare_complete("OUT", Rel.DIRECTOR_OF)
          .declare_complete("OUT", Rel.RELATIVE_OF)
          .declare_complete("OUT", Rel.PARTNER_IN)
          .declare_complete("OUT", Rel.MEMBER_OF)
          .declare_complete("DIR", Rel.PARTNER_IN)
          .declare_complete("DIR", Rel.MEMBER_OF)
          .with_relationship(Relationship("DIR", Rel.HOLDS_SHARES_IN, "OUT", percent=0.0)))
    d7 = assess(LoanFacts("CO", "OUT"), g7)
    check(d7.status == NOT_CAUGHT,
          f"a provably-unrelated party is NOT_CAUGHT ({d7.status}: {d7.reason[:40]})")

    # ── an exemption fact left UNKNOWN is not an exemption ───────────────────
    d8 = assess(LoanFacts("CO", "DIR", counterparty_is_wholly_owned_subsidiary=None), base())
    check(d8.status == PROHIBITED,
          "an unknown WOS flag does not exempt a loan that (1) prohibits")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
