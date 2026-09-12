"""Ten questions an Indian buyer asks that are hard to answer, run against the code.

A feature review that ends in a document proves nothing. This is the review as a
harness: ten questions a corporate lawyer in India actually asks about the MCA
Master Data Strip, each one wired to the modules that would have to answer it, so a
claim that "the strip handles that" fails here rather than in a meeting.

## Four outcomes, and only one of them is fatal

    ANSWERED           we produce a substantive answer we can support
    REFUSED_CORRECTLY  we decline, and name what is missing -- a good outcome
    GAP                nothing in the system addresses this; a roadmap item
    OVERCLAIMED        we answer beyond what the evidence supports

`shadow.py` established the shape: only LEAKED must be zero. Here only OVERCLAIMED
must be zero. A GAP is a thing to build; an OVERCLAIM is a thing that loses a
client, and in this market it loses them permanently, because the person who
catches it is the person who was going to sign.

Q6 was this harness's one GAP -- a share purchase agreement names four companies
and nothing decided which one the bar was about. `party_resolution.py` was written
to answer it and the outcome moved to ANSWERED. That is the loop this file exists
for: the simulation names the hole, the hole gets code, the harness proves it.

## The comparison column is measured, not asserted

Each question carries `spec_cell` -- the literal text the pasted spec's strip would
render. It is passed through `mca_reconcile.Finding`, whose constructor rejects
legal conclusions. Whether the spec overclaims is therefore decided by the same
guard that governs our own output, not by an opinion about the spec.

Run: python3 checker/buyer_sim.py
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable

from checker.mca_reconcile import (AGREES, BLOCKING, CONFLICTS, DOCUMENT_SILENT,
                                   MATERIAL, QUESTION, REFUSED, REGISTRY_SILENT,
                                   UNRESOLVABLE, ClassCapital, Finding, Overclaim,
                                   capital_headroom, charge_warranty, din_reliance)
from checker.mca_snapshot import (ABSENT, BOUNDED_BLIND, FETCH_STALE, UNBOUNDED_BLIND,
                                  Assessment, Snapshot, assess, may_assert_absence)
from checker.party_resolution import (ACQUIRER, GUARANTOR, ISSUER, ROLE_ABSENT,
                                      RULE_NEEDS, SELLER, TARGET, Party, subjects)

ANSWERED = "ANSWERED"
REFUSED_CORRECTLY = "REFUSED_CORRECTLY"
GAP = "GAP"
OVERCLAIMED = "OVERCLAIMED"

TODAY = date(2026, 9, 12)
SOURCE = "MCA21 via contracted aggregator"


@dataclass(frozen=True)
class Buyer:
    name: str
    role: str


PARTNER = Buyer("M&A partner", "Indian full-service firm, buy-side")
GC = Buyer("General counsel", "listed mid-cap, Bengaluru")
INHOUSE = Buyer("In-house legal", "building-materials group, the first real prospect")


@dataclass(frozen=True)
class Question:
    id: str
    buyer: Buyer
    text: str
    spec_cell: str                  # what the pasted spec's strip renders
    probe: Callable[[], tuple[str, str]]
    field: str = ""                 # the master-data field the cell renders, if any


@dataclass(frozen=True)
class Result:
    q: Question
    outcome: str
    answer: str
    spec_overclaims: bool          # the cell states a legal conclusion
    spec_hides_blindness: bool     # the cell renders a blind field as a settled one


def spec_overclaims(cell: str) -> bool:
    """Does the spec's own cell text trip the conclusion guard?"""
    try:
        Finding("x", cell, CONFLICTS, MATERIAL, "doc", "registry", "resolve this")
        return False
    except Overclaim:
        return True


# Phrases that would tell a reader the number in front of them is bounded rather
# than settled. A cell containing none of them, for a field the Act leaves blind,
# is rendering a floor as a fact -- the second and far more common overclaim, and
# the one the conclusion guard cannot see.
_BLINDNESS_MARKERS = ("floor", "window", "may ", "not yet", "s.77", "s.82", "s.64",
                      "s.39", "bound", "at least", "at most", "unconfirmed",
                      "blind", "ceiling")


def spec_hides_blindness(cell: str, field: str) -> bool:
    """Does this cell render a field the Act leaves blind, without saying so?"""
    if not field:
        return False
    if assess(_snap(**{field: _PROBE_VALUE}), field, TODAY).state not in (
            BOUNDED_BLIND, UNBOUNDED_BLIND):
        return False
    low = cell.lower()
    return not any(m in low for m in _BLINDNESS_MARKERS)


_PROBE_VALUE = 1   # any non-absent value; assess only needs the key to be present


def _snap(**values) -> Snapshot:
    return Snapshot("U72200KA2021PTC145892", TODAY, SOURCE, values)


# ── the probes ───────────────────────────────────────────────────────────────

def _q1() -> tuple[str, str]:
    """Zero charges on the index, a charge created 18 days ago."""
    s = _snap(charges=[])
    b = assess(s, "charges", TODAY)
    f = charge_warranty(document_states_unencumbered=True, registry_charges=(),
                        blindness=b, clause_ref="Cl 5.1")
    if f.verdict == AGREES:
        return OVERCLAIMED, "we rendered an empty index as confirmation"
    gap_days = (TODAY - b.floor_blind_since).days
    return REFUSED_CORRECTLY, (
        f"{f.verdict}. A charge created inside {gap_days} days may lawfully be "
        f"unregistered (s.77(1) first proviso), so eighteen days ago is inside our "
        f"blind window and the empty index is a floor. {f.question}")


def _q2() -> tuple[str, str]:
    """Which section makes a deactivated DIN an invalid signatory?"""
    s = _snap(din_status={"08412345": "DEACTIVATED"})
    f = din_reliance(din="08412345", registry_status="DEACTIVATED",
                     blindness=assess(s, "din_status", TODAY), role="signatory")
    if f.severity == BLOCKING:
        return OVERCLAIMED, "we blocked execution on a filing-system status"
    return REFUSED_CORRECTLY, (
        f"None does. {f.question} Cited: {', '.join(f.citations)}")


def _q3() -> tuple[str, str]:
    """Charge repaid in March, CHG-4 pending. Will you call it a breach?"""
    s = _snap(charges=[{"holder": "ICICI Bank", "amount": 25_000_000}])
    f = charge_warranty(document_states_unencumbered=True,
                        registry_charges=({"holder": "ICICI Bank",
                                           "amount": 25_000_000},),
                        blindness=assess(s, "charges", TODAY))
    if f.severity == BLOCKING or "breach" in f.question.lower():
        return OVERCLAIMED, "we called a pending satisfaction a breach"
    if "three-hundred-day" not in f.question:
        return GAP, "we did not raise the satisfaction window as an explanation"
    return ANSWERED, (f"{f.verdict}/{f.severity}, and the satisfaction window is the "
                      f"first explanation offered, not an afterthought. {f.question}")


def _q4() -> tuple[str, str]:
    """Issue at Rs 190 on Rs 10 face value -- has authorised capital been exceeded?"""
    classes = (ClassCapital("equity", 10, 50_000_000, 32_000_000),)
    bounded = Assessment(BOUNDED_BLIND, "paid_up_capital", date(2026, 8, 13))
    f = capital_headroom(new_shares=1_000_000, class_name="equity", classes=classes,
                         issued_blindness=bounded)
    consumed = 1_000_000 * 10
    if f.verdict == CONFLICTS:
        return OVERCLAIMED, "we counted premium against authorised capital"
    return ANSWERED, (
        f"No. The issue consumes Rs {consumed:,} of nominal, not Rs 19,00,00,000: "
        f"s.52(1) sends the premium to the securities premium account. "
        f"Verdict {f.verdict} against headroom of Rs 1.80 Cr.")


def _q5() -> tuple[str, str]:
    """Arbitration in 2029 -- can you produce what MCA said on signing day?"""
    s = _snap(charges=[])
    if s.evidence_grade != "SECONDARY":
        return OVERCLAIMED, "we graded an aggregator payload as primary evidence"
    return ANSWERED, (
        "Not as primary evidence. A hash of an aggregator payload proves we did not "
        "alter what we received; it does not prove the registry said it. The "
        "admissible artefact is an MCA-issued signed document, and "
        "scripts/verify_document.py checks that signature against the CCA India "
        "chain. The snapshot is graded SECONDARY in the record so nobody discovers "
        "this in cross-examination.")


def _q6() -> tuple[str, str]:
    """An SPA names four CINs. Whose master data is on the bar?"""
    doc_date = date(2026, 6, 14)
    target, acquirer = "U72200KA2021PTC145892", "L27100MH1995PLC084781"
    seller, holdco = "U65990MH2011PTC221344", "U74999DL2018PLC337761"
    parties = (Party(target, TARGET, span="(the 'Target')"),
               Party(acquirer, ACQUIRER, span="(the 'Acquirer')"),
               Party(acquirer, ISSUER, span="the Acquirer shall allot"),
               Party(seller, SELLER, span="(the 'Seller')"),
               Party(holdco, GUARANTOR, span="(the 'Guarantor')"))
    got = subjects(parties, document_date=doc_date)

    # The overclaim to guard: a rule resolving to a company the document never put
    # in the role that rule needs.
    for rule, res in got.items():
        if res.usable and not any(p.cin == res.cin and p.role == RULE_NEEDS[rule]
                                  and p.span for p in parties):
            return OVERCLAIMED, f"{rule} resolved to {res.cin} with no evidence of role"

    return ANSWERED, (
        f"None of them, and that was the wrong question -- a CIN is never a party, a "
        f"role is. Each rule needs a different one: capital headroom runs against the "
        f"ISSUER ({got['capital_headroom'].cin}), the encumbrance warranty against the "
        f"TARGET ({got['charge_warranty'].cin}), and DIN reliance against the "
        f"executing entity, which this document never identifies -- so that rule "
        f"returns {got['din_reliance'].verdict} and names the role it is missing "
        f"rather than reaching for whichever CIN came first.")


def _q7() -> tuple[str, str]:
    """MOA splits Rs 5 Cr into Rs 4 Cr equity and Rs 1 Cr preference."""
    agg = capital_headroom(new_shares=3_000_000, class_name="equity", classes=None,
                           aggregate_authorised=50_000_000)
    if agg.verdict != REFUSED:
        return OVERCLAIMED, "we answered a per-class question from an aggregate"
    split = (ClassCapital("equity", 10, 40_000_000, 32_000_000),
             ClassCapital("preference", 10, 10_000_000, 0))
    f = capital_headroom(new_shares=3_000_000, class_name="equity", classes=split,
                         issued_blindness=Assessment(BOUNDED_BLIND, "paid_up_capital",
                                                     date(2026, 8, 13)))
    return ANSWERED, (
        f"From the aggregate, no -- {agg.verdict}, because s.4(1)(e)(i) registers "
        f"the division and headroom is per class. Given the split: {f.verdict}. "
        f"Rs 3 Cr of new equity nominal against Rs 0.80 Cr of equity headroom. The "
        f"preference crore is not available to an equity allotment, which is the "
        f"answer an aggregate bar would have got wrong.")


def _q8() -> tuple[str, str]:
    """Paid-up shows Rs 3.20 Cr and we allotted last week. How stale is it?"""
    a = assess(_snap(paid_up_capital=32_000_000), "paid_up_capital", TODAY)
    if a.state != UNBOUNDED_BLIND:
        return OVERCLAIMED, "we bounded a window from a rule we do not hold"
    return REFUSED_CORRECTLY, (
        f"We cannot tell you, and that is the honest answer. {a.sentence()} s.39(4) "
        f"requires the return of allotment 'in such manner as may be prescribed' and "
        f"states no period; the period lives in a rule we have not acquired. Every "
        f"other product on this list would show you a number.")


def _q9() -> tuple[str, str]:
    """I can pull master data off the portal for free. Why pay you?"""
    s = _snap(charges=[], authorised_capital=50_000_000)
    f = charge_warranty(document_states_unencumbered=True, registry_charges=(),
                        blindness=assess(s, "charges", TODAY))
    has_record = bool(f.citations) and bool(f.blindness) and bool(f.question)
    if not has_record:
        return GAP, "we produce no dated record the portal does not"
    return ANSWERED, (
        "You can, and you should -- the data is not the product. The portal gives "
        "you a number. It does not tell you that the number is a floor for sixty "
        "days under s.77, it does not record that this document was checked against "
        "it on this date, and it does not refuse. What you are paying for is the "
        "dated refusal, which is the part that is worth something when the deal is "
        "argued about three years later.")


def _q10() -> tuple[str, str]:
    """Your bar said '0 conflicts', we signed, a charge surfaced. Who is liable?"""
    # The structural answer: prove the engine has no path to an all-clear on charges.
    b = assess(_snap(charges=[]), "charges", TODAY)
    verdicts = set()
    for doc_state in (True, False, None):
        for reg in ((), ({"holder": "X"},), None):
            verdicts.add(charge_warranty(document_states_unencumbered=doc_state,
                                         registry_charges=reg, blindness=b).verdict)
    if AGREES in verdicts:
        return OVERCLAIMED, f"the engine can emit an all-clear on charges: {verdicts}"
    return ANSWERED, (
        f"The bar never says that. Across every combination of document statement "
        f"and register contents the charge rule reaches {sorted(verdicts)} and "
        f"never AGREES -- there is no input that produces an all-clear, so there is "
        f"no all-clear to have relied on. That is a property of the code, not a "
        f"promise in a contract.")


QUESTIONS: tuple[Question, ...] = (
    Question("Q1", PARTNER,
             "Your bar shows zero charges. My client's lender created a charge "
             "eighteen days ago. What does that green tick mean?",
             "MCA Reconciled (0 Conflicts)", _q1, "charges"),
    Question("Q2", GC,
             "You told my board my CFO is an invalid signatory because his DIN is "
             "deactivated. Which section says that?",
             "Signatory Invalid: Rectify before EGM", _q2, "din_status"),
    Question("Q3", PARTNER,
             "The index shows an ICICI charge. We repaid ICICI in March and the "
             "CHG-4 is pending. Are you going to tell every counterparty we "
             "breached a warranty?",
             "Warranties Breached: Attach CHG-4 NOC", _q3, "charges"),
    Question("Q4", GC,
             "We are issuing at Rs 190 on a Rs 10 face value. Your capital check "
             "says we have blown through authorised capital. Have we?",
             "Flagged: Insert CP - File Form SH-7", _q4, "authorised_capital"),
    Question("Q5", INHOUSE,
             "If this goes to arbitration in 2029, can you produce what MCA said "
             "on the signing date, in a form a tribunal will accept?",
             "Cryptographic snapshot: legally admissible point-in-time record", _q5),
    Question("Q6", PARTNER,
             "This SPA names four CINs -- target, seller, acquirer, holdco. Whose "
             "master data is on your bar?",
             "Active CIN: U72200KA2021PTC145892", _q6),
    Question("Q7", GC,
             "Your bar says authorised Rs 5 Cr. Our memorandum splits that into "
             "Rs 4 Cr equity and Rs 1 Cr preference, and we are issuing equity. "
             "Is there headroom?",
             "Auth Cap: Rs 5.00 Cr", _q7, "authorised_capital"),
    Question("Q8", INHOUSE,
             "Paid-up shows Rs 3.20 Cr. We allotted last week. How stale is that "
             "number?",
             "Paid-Up: Rs 3.20 Cr (Synced 14m ago)", _q8, "paid_up_capital"),
    Question("Q9", PARTNER,
             "I can pull master data off the MCA portal myself for free. Why am I "
             "paying you for it?",
             "Live synchronisation with MCA21 V3", _q9, "charges"),
    Question("Q10", GC,
             "Your bar said MCA Reconciled, zero conflicts. We signed. A charge "
             "from twenty days before signing has surfaced. Who is liable?",
             "Audit Health: Green - MCA Reconciled (0 Conflicts)", _q10, "charges"),
)


def run() -> tuple[Result, ...]:
    out = []
    for q in QUESTIONS:
        outcome, answer = q.probe()
        out.append(Result(q, outcome, answer, spec_overclaims(q.spec_cell),
                          spec_hides_blindness(q.spec_cell, q.field)))
    return tuple(out)


def report(results: tuple[Result, ...]) -> str:
    lines = ["", "  id  buyer              outcome            states a   hides",
             "                                                 conclusion blindness",
             "  " + "-" * 66]
    for r in results:
        lines.append(f"  {r.q.id:<3} {r.q.buyer.name:<18} {r.outcome:<18} "
                     f"{'YES' if r.spec_overclaims else 'no':<10} "
                     f"{'YES' if r.spec_hides_blindness else '-'}")
    tally: dict[str, int] = {}
    for r in results:
        tally[r.outcome] = tally.get(r.outcome, 0) + 1
    rendering = [r for r in results if r.q.field]
    lines += ["", f"  {tally}",
              f"  spec cells stating a legal conclusion: "
              f"{sum(r.spec_overclaims for r in results)}/{len(results)}",
              f"  spec cells rendering a blind field as settled: "
              f"{sum(r.spec_hides_blindness for r in results)}/{len(rendering)}"]
    return "\n".join(lines)


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond: ok += 1; print(f"  [ok]   {label}")
        else: fail += 1; print(f"  [FAIL] {label}")

    print("buyer_sim")
    results = run()
    print(report(results))
    print()

    over = [r for r in results if r.outcome == OVERCLAIMED]
    check(not over, "no question is answered beyond the evidence -- OVERCLAIMED is 0"
                    + ("" if not over else f": {[r.q.id for r in over]}"))

    gaps = [r for r in results if r.outcome == GAP]
    check(not gaps, f"no question is left unaddressed -- Q6 was this harness's one "
                    f"GAP and party_resolution.py closed it"
                    + ("" if not gaps else f": {[r.q.id for r in gaps]}"))

    refused = [r for r in results if r.outcome == REFUSED_CORRECTLY]
    check(len(refused) >= 3,
          f"at least three of ten are refusals rather than answers ({len(refused)}) "
          f"-- a strip that answers everything is the failure mode")

    # ── the comparison is measured by the guard, not asserted ────────────────
    tripped = [r.q.id for r in results if r.spec_overclaims]
    check(set(tripped) >= {"Q2", "Q3"},
          f"the spec's own cell text trips the conclusion guard on the DIN and "
          f"charge cells ({tripped})")
    check(not spec_overclaims("Auth Cap: Rs 5.00 Cr"),
          "...and the guard is not simply rejecting everything -- a plain figure passes")

    # ── the second guard: the overclaim the first one cannot see ─────────────
    rendering = [r for r in results if r.q.field]
    hidden = [r.q.id for r in rendering if r.spec_hides_blindness]
    check(len(hidden) == len(rendering),
          f"every spec cell that renders a field the Act leaves blind renders it as "
          f"settled ({len(hidden)}/{len(rendering)}: {hidden}) -- this, not the "
          f"wording, is the defect that repeats")
    check(not spec_hides_blindness(
              "Active Charges: 0 -- a floor; s.77 allows 60 days to register",
              "charges"),
          "...and a cell that states the window passes, so the guard measures the "
          "disclosure and not the topic")

    # ── every answer is substantive ──────────────────────────────────────────
    check(all(len(r.answer) > 80 for r in results),
          "every question produces a real answer, not a status word")
    check(all(r.q.spec_cell for r in results),
          "every question records what the pasted spec would have rendered")

    # ── the structural claim in Q10 is the one that must not rot ─────────────
    q10 = [r for r in results if r.q.id == "Q10"][0]
    check("never AGREES" in q10.answer,
          "Q10 rests on an exhaustive sweep of the charge rule, not on a promise")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
