"""s.188 — related-party transactions: is a contract caught, and what does it need?

A transaction-scoped decider grounded in the corpus text of s.188 and the s.2(76)
"related party" definition (read, not recalled).

s.188(1): a company may not enter a contract of the listed TYPES (a)-(g) — sale/
purchase/supply of goods, buying/selling/leasing property, availing/rendering
services, appointing an agent, a related party's appointment to an office of
profit, underwriting securities — with a RELATED PARTY, except with a Board
resolution. First proviso: above a PRESCRIBED capital/transaction threshold, prior
approval by a members' resolution is also required. Fourth proviso: nothing
applies to a transaction in the ordinary course of business that is on an arm's
length basis. Fifth proviso: the members' resolution is not needed for a holding->
wholly-owned-subsidiary transaction with consolidated accounts.

## Two honest boundaries

1. The members'-approval threshold is set by DELEGATED RULE (the first proviso's
   "such amount ... as may be prescribed"), which this corpus does not hold — the
   same S-002-class gap as the small-company limits. So this decider can say a
   related-party transaction needs AT LEAST a Board resolution, but whether a
   members' resolution is ALSO required is UNDETERMINED and names the unacquired
   rule, rather than guessing a number.

2. The s.2(76) related-party test has limbs this graph does not model — key
   managerial personnel / manager relations (unless supplied), and the
   "accustomed to act" limbs (vi)/(vii) and the prescribed limb (ix). So a
   positive relation is found from the modelled limbs; a NEGATIVE ("not a related
   party") is only returned when the modelled limbs are provably absent AND the
   caller asserts there are no unmodelled relations. Otherwise UNKNOWN.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from checker.entity_graph import Answer, EntityGraph, Kind, Rel

# The transaction types s.188(1)(a)-(g) reaches. A transaction of any other type
# is simply not within s.188.
class TxnType(str, Enum):
    GOODS = "sale_purchase_supply_of_goods"          # (a)
    PROPERTY_TRADE = "buying_or_selling_property"    # (b)
    PROPERTY_LEASE = "leasing_property"              # (c)
    SERVICES = "availing_or_rendering_services"      # (d)
    AGENT = "appointment_of_agent"                   # (e)
    OFFICE_OF_PROFIT = "related_party_office_of_profit"  # (f)
    UNDERWRITING = "underwriting_securities"         # (g)


NEEDS_BOARD_RESOLUTION = "NEEDS_BOARD_RESOLUTION"
NEEDS_MEMBER_APPROVAL = "NEEDS_MEMBER_APPROVAL"                     # determinate: above the threshold
NEEDS_MEMBER_APPROVAL_UNDETERMINED = "NEEDS_MEMBER_APPROVAL_UNDETERMINED"
EXEMPT = "EXEMPT"
NOT_CAUGHT = "NOT_CAUGHT"
CANNOT_DETERMINE = "CANNOT_DETERMINE"

PROVISION = "Companies Act 2013, s.188"
# The delegated rule that sets the members'-approval threshold (first proviso).
MEMBER_THRESHOLD_TASK = "S-188-RULES"


@dataclass(frozen=True)
class TxnFacts:
    company: str
    counterparty: str
    txn_type: TxnType
    # fourth-proviso exemption, tri-valued (None = unknown):
    ordinary_course_of_business: bool | None = None
    arms_length: bool | None = None
    # fifth-proviso: holding -> wholly-owned-subsidiary with consolidated accounts
    holding_to_wos_consolidated: bool | None = None
    # KMP / managers of the company the caller knows (extends the s.2(76) limbs)
    kmp_or_managers: tuple[str, ...] = ()
    # caller asserts there are no unmodelled related-party relations (KMP-based,
    # accustomed-to-act, prescribed). Only then may a NEGATIVE be returned.
    no_unmodelled_relations: bool = False
    # financials for the first-proviso members'-approval threshold (Rule 15). Money
    # or None; None = unknown (never treated as under). Used only once the threshold
    # rule is reviewed+attested (checker.s188_threshold); ignored until then.
    transaction_value: "object | None" = None      # a company_profile.Money
    turnover: "object | None" = None
    net_worth: "object | None" = None
    paid_up_capital: "object | None" = None


@dataclass(frozen=True)
class Determination:
    status: str
    reason: str
    conditions: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    blocked_by: str = ""

    @property
    def needs_attention(self) -> bool:
        return self.status in (NEEDS_BOARD_RESOLUTION, NEEDS_MEMBER_APPROVAL,
                               NEEDS_MEMBER_APPROVAL_UNDETERMINED, CANNOT_DETERMINE)


def related_party(company: str, cp: str, graph: EntityGraph,
                  *, kmp: tuple[str, ...] = (),
                  assume_no_unmodelled: bool = False) -> Answer:
    """s.2(76) related-party test on the graph. Tri-state.

    Persons of interest = the company's directors plus any supplied KMP/managers.
    A YES is returned from any modelled limb. A NO only when every modelled limb
    is provably absent AND `assume_no_unmodelled` is set (the caller vouching that
    the KMP/accustomed-to-act/prescribed limbs do not apply). Otherwise UNKNOWN.
    """
    poi = list(dict.fromkeys(list(graph.directors_of(company)) + list(kmp)))

    def yes(a: Answer) -> bool:
        return a is Answer.YES

    # (i)/(ii): cp is a person of interest, or a relative of one.
    if cp in poi:
        return Answer.YES
    if any(yes(graph.are_relatives(cp, p)) for p in poi):
        return Answer.YES
    # (iii): cp is a firm in which such a person (or their relative) is a partner.
    if any(yes(graph.holds(p, Rel.PARTNER_IN, cp)) for p in poi):
        return Answer.YES
    # (iv): cp is a company in which such a person is a member or a director.
    if any(yes(graph.holds(p, Rel.MEMBER_OF, cp)) or yes(graph.holds(p, Rel.DIRECTOR_OF, cp))
           for p in poi):
        return Answer.YES
    # (v): cp is a public company in which such a person is a director AND holds,
    # with relatives, more than two per cent. (shareholding proxy for that stake).
    for p in poi:
        if yes(graph.holds(p, Rel.DIRECTOR_OF, cp)):
            pct = graph.shareholding(p, cp)
            if pct is not None and pct > 2.0:
                return Answer.YES
    # (viii): cp is a holding, subsidiary or associate of the company.
    if (yes(graph.holds(cp, Rel.CONTROLS, company))
            or yes(graph.holds(company, Rel.CONTROLS, cp))):
        return Answer.YES

    # No modelled limb matched. A NEGATIVE is only honest under an explicit
    # vouch that the unmodelled limbs do not apply; else UNKNOWN.
    return Answer.NO if assume_no_unmodelled else Answer.UNKNOWN


def assess(facts: TxnFacts, graph: EntityGraph) -> Determination:
    # s.188 only reaches the listed transaction types. Anything else is outside it.
    if not isinstance(facts.txn_type, TxnType):
        return Determination(NOT_CAUGHT, "transaction type is not one s.188 lists")

    rp = related_party(facts.company, facts.counterparty, graph,
                       kmp=facts.kmp_or_managers,
                       assume_no_unmodelled=facts.no_unmodelled_relations)

    if rp is Answer.NO:
        return Determination(NOT_CAUGHT,
                             "the counterparty is not a related party under s.2(76)")
    if rp is Answer.UNKNOWN:
        return Determination(CANNOT_DETERMINE,
                             "cannot establish whether the counterparty is a related party "
                             "(s.2(76)); modelled limbs did not match and unmodelled limbs "
                             "(KMP/manager, accustomed-to-act, prescribed) are not ruled out",
                             missing=("the company's KMP/managers, and a vouch that no "
                                      "accustomed-to-act or prescribed relation applies",))

    # rp is YES: a related-party transaction of a caught type.
    # Fourth proviso: ordinary course AND arm's length -> not caught.
    if facts.ordinary_course_of_business is True and facts.arms_length is True:
        return Determination(EXEMPT,
                             "a related-party transaction, but in the ordinary course of "
                             "business and on an arm's length basis (s.188 fourth proviso)")

    conditions = ("consent of the Board by a resolution at a Board meeting (s.188(1))",)
    # Fifth proviso: holding -> WOS with consolidated accounts removes the members'
    # resolution requirement (but not the Board consent).
    if facts.holding_to_wos_consolidated is True:
        return Determination(NEEDS_BOARD_RESOLUTION,
                             "a related-party transaction (holding -> wholly-owned "
                             "subsidiary, accounts consolidated): Board resolution required; "
                             "the members' resolution is not (s.188 fifth proviso)",
                             conditions=conditions)

    # Board resolution is required; whether a members' resolution is ALSO required
    # turns on the first-proviso threshold (Rule 15). Consult the reviewed threshold:
    # if it is not yet attested we refuse (naming the task); once attested we resolve.
    from checker import s188_threshold as thr
    servable, why = thr.available()
    if not servable:
        return Determination(NEEDS_MEMBER_APPROVAL_UNDETERMINED,
                             "a related-party transaction of a caught type: a Board resolution "
                             "is required (s.188(1)); whether a members' resolution is ALSO "
                             "required depends on the prescribed capital/transaction threshold "
                             "(first proviso), a delegated rule not yet reviewed",
                             conditions=conditions + (
                                 "if above the prescribed threshold, prior approval by a members' "
                                 "resolution, on which a related-party member may not vote "
                                 "(s.188 first & second provisos)",),
                             blocked_by=MEMBER_THRESHOLD_TASK)

    from datetime import date as _date
    threshold = thr.lookup(_date.today())
    crossed = threshold.crosses(txn_value=facts.transaction_value,
                                turnover=facts.turnover, net_worth=facts.net_worth,
                                paid_up_capital=facts.paid_up_capital)
    if crossed is True:
        return Determination(NEEDS_MEMBER_APPROVAL,
                             "a related-party transaction ABOVE the prescribed threshold "
                             f"({threshold.instrument}): a Board resolution AND prior members' "
                             "approval are required (s.188(1) & first proviso)",
                             conditions=conditions + (
                                 "prior approval by a members' resolution; a related-party "
                                 "member may not vote on it (s.188 first & second provisos)",))
    if crossed is False:
        return Determination(NEEDS_BOARD_RESOLUTION,
                             "a related-party transaction BELOW the prescribed threshold "
                             f"({threshold.instrument}): a Board resolution is required; a "
                             "members' resolution is not (s.188(1))",
                             conditions=conditions)
    return Determination(CANNOT_DETERMINE,
                         "a related-party transaction of a caught type; a Board resolution is "
                         "required, but the members'-approval threshold cannot be tested while "
                         "a needed figure is unknown (an unknown figure is not treated as below)",
                         conditions=conditions,
                         missing=("the transaction value, and the company's turnover / net worth "
                                  "/ paid-up capital, to test the first-proviso threshold",))


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

    print("s188")
    from checker.entity_graph import Entity, Relationship

    def base():
        return (EntityGraph()
                .with_entity(Entity("CO", Kind.COMPANY))
                .with_entity(Entity("DIR", Kind.INDIVIDUAL))
                .with_entity(Entity("REL", Kind.INDIVIDUAL))
                .with_entity(Entity("FIRM", Kind.COMPANY))
                .with_entity(Entity("VENDOR", Kind.COMPANY))
                .with_relationship(Relationship("DIR", Rel.DIRECTOR_OF, "CO")))

    # ── a director's firm as counterparty: related party, caught type ───────
    g = base().with_relationship(Relationship("DIR", Rel.PARTNER_IN, "FIRM"))
    d = assess(TxnFacts("CO", "FIRM", TxnType.GOODS), g)
    check(d.status == NEEDS_MEMBER_APPROVAL_UNDETERMINED,
          f"a goods contract with a director's firm needs >= Board resolution ({d.status})")
    check(d.blocked_by == MEMBER_THRESHOLD_TASK,
          "...and flags the unacquired members'-threshold rule")
    check(any("Board" in c for c in d.conditions), "...naming the Board-resolution condition")

    # ── the arm's-length ordinary-course exemption ──────────────────────────
    d2 = assess(TxnFacts("CO", "FIRM", TxnType.GOODS,
                         ordinary_course_of_business=True, arms_length=True), g)
    check(d2.status == EXEMPT, f"ordinary course + arm's length is EXEMPT ({d2.status})")
    # ...but not if only one holds
    d2b = assess(TxnFacts("CO", "FIRM", TxnType.GOODS,
                          ordinary_course_of_business=True, arms_length=False), g)
    check(d2b.status == NEEDS_MEMBER_APPROVAL_UNDETERMINED,
          "ordinary course WITHOUT arm's length is not exempt")

    # ── a director's relative ───────────────────────────────────────────────
    g3 = base().with_relationship(Relationship("REL", Rel.RELATIVE_OF, "DIR"))
    d3 = assess(TxnFacts("CO", "REL", TxnType.SERVICES), g3)
    check(d3.status == NEEDS_MEMBER_APPROVAL_UNDETERMINED,
          "a services contract with a director's relative is caught")

    # ── holding -> WOS consolidated: Board only, no members' resolution ─────
    d4 = assess(TxnFacts("CO", "FIRM", TxnType.GOODS, holding_to_wos_consolidated=True), g)
    check(d4.status == NEEDS_BOARD_RESOLUTION,
          f"holding->WOS consolidated needs Board resolution only ({d4.status})")

    # ── an unrelated vendor, relations not ruled out -> CANNOT_DETERMINE ────
    d5 = assess(TxnFacts("CO", "VENDOR", TxnType.GOODS), base())
    check(d5.status == CANNOT_DETERMINE,
          f"an unestablished related-party status is CANNOT_DETERMINE ({d5.status})")
    check(bool(d5.missing), "...and names what would settle it")

    # ── an unrelated vendor, relations vouched absent -> NOT_CAUGHT ─────────
    g6 = (base().declare_complete_into("CO", Rel.DIRECTOR_OF))
    d6 = assess(TxnFacts("CO", "VENDOR", TxnType.GOODS, no_unmodelled_relations=True), g6)
    check(d6.status == NOT_CAUGHT,
          f"a vouched non-related party is NOT_CAUGHT ({d6.status})")

    # ── s.2(76)(v): public company, director + >2% holding ──────────────────
    g7 = (base().with_relationship(Relationship("DIR", Rel.DIRECTOR_OF, "VENDOR"))
          .with_relationship(Relationship("DIR", Rel.HOLDS_SHARES_IN, "VENDOR", percent=3.0)))
    check(related_party("CO", "VENDOR", g7) is Answer.YES,
          "a director-directorship + >2% holding makes the counterparty related (s.2(76)(v))")

    # ── KMP limb via supplied kmp ids ───────────────────────────────────────
    g8 = (base().with_entity(Entity("KMP", Kind.INDIVIDUAL))
          .with_entity(Entity("KFIRM", Kind.COMPANY))
          .with_relationship(Relationship("KMP", Rel.PARTNER_IN, "KFIRM")))
    check(related_party("CO", "KFIRM", g8, kmp=("KMP",)) is Answer.YES,
          "a firm in which a supplied KMP is a partner is related (s.2(76)(iii))")

    # ── D1: once Rule 15 is reviewed+attested, the threshold RESOLVES ───────
    # Mock the reviewed threshold (a reviewer having set the limbs); the live path
    # stays UNDETERMINED until a real record is attested (tested above).
    from unittest import mock
    import checker.s188_threshold as thr
    from checker.company_profile import Money
    stub = thr.attested_stub()  # 10cr floor, 10% turnover, 10% net worth
    with mock.patch.object(thr, "available", lambda: (True, "attested [stub]")), \
         mock.patch.object(thr, "lookup", lambda _as_of: stub):
        # a large transaction (> 10% turnover) -> determinate MEMBER approval
        big = assess(TxnFacts("CO", "FIRM", TxnType.GOODS,
                              transaction_value=Money.crore(5), turnover=Money.crore(30),
                              net_worth=Money.crore(20), paid_up_capital=Money.crore(2)), g)
        check(big.status == NEEDS_MEMBER_APPROVAL,
              f"above the threshold resolves to NEEDS_MEMBER_APPROVAL ({big.status})")
        check("Rule 15" in big.reason, "...citing the reviewed rule")
        # a small transaction, small company -> board resolution only
        below = assess(TxnFacts("CO", "FIRM", TxnType.GOODS,
                                transaction_value=Money.lakh(1), turnover=Money.crore(30),
                                net_worth=Money.crore(20), paid_up_capital=Money.crore(2)), g)
        check(below.status == NEEDS_BOARD_RESOLUTION,
              f"below the threshold resolves to Board resolution only ({below.status})")
        # unknown financials -> CANNOT_DETERMINE, never silently 'below'
        unk = assess(TxnFacts("CO", "FIRM", TxnType.GOODS), g)
        check(unk.status == CANNOT_DETERMINE,
              f"an unknown transaction value cannot be tested against the threshold ({unk.status})")
        check(bool(unk.missing), "...and names the figures needed")

    # And with the threshold UNAVAILABLE (the real state today) it still refuses.
    with mock.patch.object(thr, "available", lambda: (False, "S-188-RULES not attested")):
        refused = assess(TxnFacts("CO", "FIRM", TxnType.GOODS), g)
        check(refused.status == NEEDS_MEMBER_APPROVAL_UNDETERMINED
              and refused.blocked_by == MEMBER_THRESHOLD_TASK,
              "with Rule 15 unattested, s188 still refuses and names S-188-RULES")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
