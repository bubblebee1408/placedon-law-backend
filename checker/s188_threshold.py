"""The s.188 members'-approval threshold — reviewable, refusing until attested.

s.188's first proviso needs a members' resolution when a related-party transaction
crosses a PRESCRIBED threshold set by Rule 15 of the Companies (Meetings of Board
and its Powers) Rules, 2014. That rule is HELD in the corpus but its extraction is
defective (its own warnings: "a reviewer must set the boundary", "557 words split")
AND its limbs were amended in 2019. So its values must NOT be served as law until a
human reviews them against a clean, dated source and attests — the same discipline
as G.S.R. 700(E) (`prescribed_thresholds` / `register_gsr700e`).

This module holds the STRUCTURE of the threshold and derives its servability from a
review record. The limb VALUES live in that record (set by a reviewer), never
hardcoded here. Until the record is attested, `lookup()` refuses and names the task
`S-188-RULES`, so `s188.assess` keeps returning NEEDS_MEMBER_APPROVAL_UNDETERMINED —
and flips to a determinate member-approval state the moment a reviewer attests.

## Unknown is not "under"

`crosses()` returns True if any reviewed limb is triggered, False only if every
applicable limb is known and none is triggered, and None if a needed figure is
unknown. An unknown turnover never silently reads as "below the threshold".
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from checker.company_profile import Money
from checker.provenance import CORROBORATED, SERVABLE, UNRESOLVED

RULE15_TASK = "S-188-RULES"
RULE15_INSTRUMENT = ("Rule 15, Companies (Meetings of Board and its Powers) "
                     "Rules, 2014 (as amended)")


@dataclass(frozen=True)
class MemberApprovalThreshold:
    """The reviewed limbs of the s.188 first proviso / Rule 15.

    Any limb may be None, meaning the reviewed rule does not use it (e.g. the 2019
    amendment removed the paid-up-capital trigger — a reviewer would set it None).
    """
    paid_up_capital_floor: Money | None      # the ">= X paid-up capital" class trigger
    pct_of_turnover: float | None            # transaction value as % of turnover
    pct_of_net_worth: float | None           # transaction value as % of net worth
    instrument: str
    state: str                               # a checker.provenance evidence state
    note: str = ""

    @property
    def servable(self) -> bool:
        return self.state in SERVABLE

    def crosses(self, *, txn_value: Money | None, turnover: Money | None,
                net_worth: Money | None,
                paid_up_capital: Money | None) -> bool | None:
        """Does the transaction trigger the members'-approval requirement?"""
        triggered = False
        any_unknown = False

        if self.paid_up_capital_floor is not None:
            if paid_up_capital is None:
                any_unknown = True
            elif paid_up_capital.rupees >= self.paid_up_capital_floor.rupees:
                triggered = True

        if self.pct_of_turnover is not None:
            if txn_value is None or turnover is None:
                any_unknown = True
            elif txn_value.rupees > turnover.rupees * self.pct_of_turnover / 100.0:
                triggered = True

        if self.pct_of_net_worth is not None:
            if txn_value is None or net_worth is None:
                any_unknown = True
            elif txn_value.rupees > net_worth.rupees * self.pct_of_net_worth / 100.0:
                triggered = True

        if triggered:
            return True
        return None if any_unknown else False


class ThresholdUnavailable(LookupError):
    """The s.188 threshold is not yet reviewable-and-attested."""


def _review_state() -> tuple[str, str, dict | None]:
    """(evidence state, note, reviewed limbs) derived from the review record."""
    try:
        from scripts.register_s188_rule15 import review_record, is_attested
    except ImportError:                                     # pragma: no cover
        return UNRESOLVED, "the s.188 review module could not be imported", None
    rec = review_record()
    if rec is None:
        return UNRESOLVED, (
            "Rule 15 (the s.188 members'-approval threshold) is held but not staged "
            f"for review. Acquire under {RULE15_TASK}: run "
            "scripts/register_s188_rule15.py to stage it, then a reviewer attests "
            "the operative limbs against a clean dated source."), None
    if not is_attested(rec):
        return UNRESOLVED, (
            "Rule 15 is staged but not attested: the extraction is defective and the "
            "limbs were amended in 2019, so a reviewer must set and attest the "
            f"operative boundary. Run scripts/register_s188_rule15.py --attest. ({RULE15_TASK})"
        ), None
    return CORROBORATED, (
        f"reviewed and attested by {rec['reviewed_by']} at {rec['reviewed_at']}"), rec.get("limbs")


def _money_or_none(v) -> Money | None:
    return Money(int(v)) if v is not None else None


def lookup(as_of: date) -> MemberApprovalThreshold:
    """The reviewed threshold, or raise if it is not attested."""
    state, note, limbs = _review_state()
    if state not in SERVABLE or limbs is None:
        raise ThresholdUnavailable(note)
    return MemberApprovalThreshold(
        paid_up_capital_floor=_money_or_none(limbs.get("paid_up_capital_floor_rupees")),
        pct_of_turnover=limbs.get("pct_of_turnover"),
        pct_of_net_worth=limbs.get("pct_of_net_worth"),
        instrument=RULE15_INSTRUMENT, state=state, note=note)


def available() -> tuple[bool, str]:
    """(is the threshold servable, the reason) — without raising."""
    state, note, _ = _review_state()
    return state in SERVABLE, note


# ── test support ──────────────────────────────────────────────────────────────
def attested_stub(*, paid_up_capital_floor_rupees=100_000_000,
                  pct_of_turnover=10.0, pct_of_net_worth=10.0) -> MemberApprovalThreshold:
    """A stub reviewed threshold for tests — represents a reviewer having set the
    limbs. NOT served law; the production path uses lookup() against a real record."""
    return MemberApprovalThreshold(
        paid_up_capital_floor=_money_or_none(paid_up_capital_floor_rupees),
        pct_of_turnover=pct_of_turnover, pct_of_net_worth=pct_of_net_worth,
        instrument=RULE15_INSTRUMENT + " [TEST STUB]", state=CORROBORATED)


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

    print("s188_threshold")

    th = attested_stub()  # 10cr floor, 10% turnover, 10% net worth

    # ── a big transaction crosses; a tiny one does not ──────────────────────
    big = th.crosses(txn_value=Money.crore(5), turnover=Money.crore(30),
                     net_worth=Money.crore(20), paid_up_capital=Money.crore(2))
    check(big is True, f"a transaction over 10% of turnover crosses ({big})")
    small = th.crosses(txn_value=Money.lakh(1), turnover=Money.crore(30),
                       net_worth=Money.crore(20), paid_up_capital=Money.crore(2))
    check(small is False, f"a small transaction under every limb does not cross ({small})")

    # ── the paid-up-capital class trigger ───────────────────────────────────
    cap = th.crosses(txn_value=Money.lakh(1), turnover=Money.crore(30),
                     net_worth=Money.crore(20), paid_up_capital=Money.crore(12))
    check(cap is True, "a >= 10cr paid-up-capital company crosses regardless of size")

    # ── unknown figure => None, never 'under' ───────────────────────────────
    unk = th.crosses(txn_value=Money.crore(5), turnover=None,
                     net_worth=None, paid_up_capital=None)
    check(unk is None, "with every figure unknown, no limb triggers => None, not False")
    # but a KNOWN trigger wins even when other figures are unknown
    known_trigger = th.crosses(txn_value=Money.lakh(1), turnover=None,
                               net_worth=None, paid_up_capital=Money.crore(12))
    check(known_trigger is True,
          "a known >=10cr capital triggers even while turnover/net-worth are unknown")
    unk2 = th.crosses(txn_value=Money.lakh(50), turnover=None,
                      net_worth=None, paid_up_capital=Money.crore(2))
    check(unk2 is None, "under the capital floor but turnover/net-worth unknown => None, not False")

    # ── a limb the reviewed rule does not use is ignored ────────────────────
    no_cap = attested_stub(paid_up_capital_floor_rupees=None)
    r = no_cap.crosses(txn_value=Money.lakh(1), turnover=Money.crore(30),
                       net_worth=Money.crore(20), paid_up_capital=Money.crore(12))
    check(r is False, "a removed paid-up-capital trigger (2019 amendment) is not applied")

    # ── the LIVE path refuses until a real record is attested ───────────────
    ok_avail, note = available()
    if not ok_avail:
        check("S-188-RULES" in note or "Rule 15" in note,
              "the live threshold refuses and names the review task")
        try:
            lookup(date(2026, 8, 31))
            check(False, "lookup raises while unattested")
        except ThresholdUnavailable:
            check(True, "lookup raises while the rule is unattested")
    else:
        check(True, "the live threshold is attested (a reviewer has set the limbs)")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
