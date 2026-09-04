"""Company classification under the Companies Act. Decided by code, never a model.

The first classification is small-company status under s.2(85), because it gates
a large set of relaxations and because it is the one practitioners most often
get wrong — the thresholds moved, the connective between the two limbs changed
from "or" to "and", and the operative numbers are not in the Act at all.

The provision, quoted from our own corpus:

    "(85) 'small company' means a company, other than a public company,--
     (i) paid-up share capital of which does not exceed fifty lakh rupees or
     such higher amount as may be prescribed ...; [and] (ii) turnover of which
     [as per profit and loss account for the immediately preceding financial
     year] does not exceed two crore rupees or such higher amount as may be
     prescribed ...: Provided that nothing in this clause shall apply to--
     (A) a holding company or a subsidiary company; (B) a company registered
     under section 8; or (C) a company or body corporate governed by any
     special Act."

## The asymmetry that governs every answer here

Being small is a RELIEF: it removes obligations. So a wrong "small" is the
dangerous direction and a wrong "not small" merely costs the user work they
did not owe. The two conclusions therefore need different standards of proof:

    NOT SMALL  one definitive failing condition is enough. A public company is
               not small whatever its turnover, and no threshold is needed to
               say so.
    SMALL      every condition must be KNOWN and satisfied. A single unknown
               exclusion is enough to withhold it.

This is why an unknown field does not simply propagate INSUFFICIENT_DATA in both
directions. It blocks the relief and does not block the refusal.

## Thresholds are looked up, not known

The operative amounts live in a delegated rule this system has not properly
acquired (see prescribed_thresholds and task S-002), so `small_company()`
answers INSUFFICIENT_DATA on the arithmetic today — while still answering
definitively wherever the arithmetic is not needed.
"""
from __future__ import annotations

from datetime import date

from applicability import Result, Trace
from checker.company_profile import (CompanyProfile, FigureYearError, Money)
from checker.prescribed_thresholds import ThresholdUnavailable, operative_small_company_limits

CAPITAL_KEY = "small_company.paid_up_capital.prescribed"
TURNOVER_KEY = "small_company.turnover.prescribed"


def _t(node: str, res: Result, detail: str, children=None) -> Trace:
    return Trace(node, res, detail, children or [])


def small_company(profile: CompanyProfile, *,
                  financial_year: str | None = None,
                  limits: tuple[Money, Money] | None = None) -> tuple[Result, Trace]:
    """Is this a small company under s.2(85)?

    APPLIES means small. DOES_NOT_APPLY means not small. INSUFFICIENT_DATA means
    we will not say, and the trace names exactly what is missing.

    `limits` lets a caller supply thresholds it has acquired by another route.
    When supplied, the trace records that they were SUPPLIED rather than looked
    up, so an answer can never silently rest on a number nobody sourced.
    """
    kids: list[Trace] = []
    as_of = profile.as_of

    # ── the proviso first: it disapplies the clause entirely ────────────────
    # Checked before the arithmetic because it needs no thresholds, so it can
    # answer definitively on a day when the thresholds are unavailable.
    exclusions = (
        ("is_holding_company", "s.2(85) proviso (A): a holding company"),
        ("is_subsidiary_company", "s.2(85) proviso (A): a subsidiary company"),
        ("is_section_8", "s.2(85) proviso (B): registered under section 8"),
        ("governed_by_special_act",
         "s.2(85) proviso (C): governed by a special Act"),
    )
    unknown_exclusions: list[str] = []
    for field_name, why in exclusions:
        v = getattr(profile, field_name, None)
        if v is True:
            kids.append(_t(field_name, Result.DOES_NOT_APPLY,
                           f"{why} — the clause does not apply"))
            return Result.DOES_NOT_APPLY, _t(
                "s.2(85)", Result.DOES_NOT_APPLY,
                "excluded by the proviso, so not a small company", kids)
        if v is None:
            unknown_exclusions.append(field_name)

    # ── "other than a public company" ───────────────────────────────────────
    if profile.company_class == "public":
        kids.append(_t("company_class", Result.DOES_NOT_APPLY,
                       "a public company is outside s.2(85) by its opening words"))
        return Result.DOES_NOT_APPLY, _t(
            "s.2(85)", Result.DOES_NOT_APPLY,
            "a public company is never a small company", kids)
    kids.append(_t("company_class", Result.APPLIES,
                   f"{profile.company_class} is not a public company"))

    # ── the financial year the turnover limb asks about ─────────────────────
    fy = financial_year or profile.latest_financial_year
    if fy is None:
        kids.append(_t("financial_year", Result.INSUFFICIENT_DATA,
                       "s.2(85)(ii) asks for turnover for the immediately "
                       "preceding financial year, and no financial year is set"))
        return Result.INSUFFICIENT_DATA, _t(
            "s.2(85)", Result.INSUFFICIENT_DATA,
            "cannot test the turnover limb without a financial year", kids)

    # ── thresholds ──────────────────────────────────────────────────────────
    if limits is not None:
        cap_limit, turn_limit = limits
        kids.append(_t("thresholds", Result.APPLIES,
                       f"limits SUPPLIED by the caller: capital {cap_limit}, "
                       f"turnover {turn_limit} — not looked up, not sourced here"))
        threshold_error: ThresholdUnavailable | None = None
    else:
        try:
            cap_limit, turn_limit = operative_small_company_limits(as_of)
            kids.append(_t("thresholds", Result.APPLIES,
                           f"prescribed limits at {as_of}: capital {cap_limit}, "
                           f"turnover {turn_limit}"))
            threshold_error = None
        except ThresholdUnavailable as e:
            cap_limit = turn_limit = None       # type: ignore[assignment]
            threshold_error = e
            kids.append(_t("thresholds", Result.INSUFFICIENT_DATA, str(e)))

    # ── the two limbs, conjunctive ──────────────────────────────────────────
    # Evaluated even when thresholds are missing, because a limb whose FIGURE is
    # unknown is a different failure from one whose LIMIT is unknown, and the
    # trace should say which.
    def limb(field_name: str, limit: Money | None, label: str) -> Result:
        try:
            amount = profile.amount_for(field_name, fy)
        except FigureYearError as e:
            kids.append(_t(field_name, Result.INSUFFICIENT_DATA, str(e)))
            return Result.INSUFFICIENT_DATA
        if amount is None:
            kids.append(_t(field_name, Result.INSUFFICIENT_DATA,
                           f"{label} is not on the profile — need it to decide"))
            return Result.INSUFFICIENT_DATA
        if limit is None:
            kids.append(_t(field_name, Result.INSUFFICIENT_DATA,
                           f"{label} is {Money(amount)} but the prescribed limit "
                           f"is not available, so no comparison can be made"))
            return Result.INSUFFICIENT_DATA
        within = amount <= limit.rupees
        kids.append(_t(field_name,
                       Result.APPLIES if within else Result.DOES_NOT_APPLY,
                       f"{label} {Money(amount)} "
                       f"{'does not exceed' if within else 'exceeds'} {limit}"))
        return Result.APPLIES if within else Result.DOES_NOT_APPLY

    cap = limb("paid_up_capital", cap_limit, "paid-up share capital")
    turn = limb("turnover", turn_limit, "turnover")

    # A limb that definitively EXCEEDS its limit settles the question, and needs
    # nothing else to be known — including the unknown exclusions above.
    if Result.DOES_NOT_APPLY in (cap, turn):
        return Result.DOES_NOT_APPLY, _t(
            "s.2(85)", Result.DOES_NOT_APPLY,
            "a limb exceeds its limit, so not a small company", kids)

    if Result.INSUFFICIENT_DATA in (cap, turn):
        return Result.INSUFFICIENT_DATA, _t(
            "s.2(85)", Result.INSUFFICIENT_DATA,
            (f"cannot decide: {threshold_error}" if threshold_error
             else "a limb could not be tested"), kids)

    # Both limbs pass. Now every exclusion must be KNOWN false before relief is
    # granted — this is the asymmetry in the module docstring.
    if unknown_exclusions:
        kids.append(_t("proviso", Result.INSUFFICIENT_DATA,
                       f"both limbs pass, but {', '.join(unknown_exclusions)} "
                       f"{'is' if len(unknown_exclusions) == 1 else 'are'} unknown; "
                       "small-company status is a relief and is not granted on an "
                       "unchecked exclusion"))
        return Result.INSUFFICIENT_DATA, _t(
            "s.2(85)", Result.INSUFFICIENT_DATA,
            "both limbs pass but an exclusion is unverified", kids)

    return Result.APPLIES, _t(
        "s.2(85)", Result.APPLIES,
        "not a public company, neither limb exceeds its prescribed limit, and "
        "no proviso exclusion applies", kids)


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

    print("classify")
    from checker.company_profile import Figure

    def prof(**kw):
        base = dict(company_class="private", incorporation_date=date(2019, 6, 1),
                    as_of=date(2026, 8, 31), latest_financial_year="2024-25",
                    is_holding_company=False, is_subsidiary_company=False,
                    is_section_8=False, governed_by_special_act=False)
        base.update(kw)
        return CompanyProfile(**base)  # type: ignore[arg-type]

    LIMITS = (Money.crore(4), Money.crore(40))
    small = prof(paid_up_capital=Figure(Money.crore(2), "2024-25"),
                 turnover=Figure(Money.crore(30), "2024-25"))

    # ── the headline: no answer while the thresholds are unacquired. Forced
    # via the stub so it does not depend on the live 700(E) attestation state. ─
    import scripts.register_gsr700e as _reg
    with _reg.stub_registration(None):
        r, tr = small_company(small)
        check(r is Result.INSUFFICIENT_DATA,
              f"with no acquired thresholds the arithmetic is refused ({r})")
        check("not servable" in tr.render() or "S-002" in tr.render(),
              "...and the trace names the acquisition gap")

    # ── and a definite answer once the thresholds are acquired ──────────────
    with _reg.stub_registration(_reg.attested_stub()):
        r_ok, _ = small_company(small)
        check(r_ok is Result.APPLIES,
              f"with acquired thresholds a small company is classified ({r_ok})")

    # ── but definitive answers that need no threshold still come out ────────
    r2, tr2 = small_company(prof(company_class="public"))
    check(r2 is Result.DOES_NOT_APPLY,
          f"a public company is not small, no threshold needed ({r2})")
    check("public company" in tr2.render(), "...and the trace says why")

    r3, _ = small_company(prof(is_section_8=True))
    check(r3 is Result.DOES_NOT_APPLY, "an s.8 company is excluded by the proviso")
    r4, tr4 = small_company(prof(is_subsidiary_company=True))
    check(r4 is Result.DOES_NOT_APPLY, "a subsidiary is excluded by the proviso")
    check("proviso (A)" in tr4.render(), f"...naming the limb ({tr4.detail})")
    r5, _ = small_company(prof(governed_by_special_act=True))
    check(r5 is Result.DOES_NOT_APPLY, "a special-Act body is excluded")

    # ── with supplied limits the arithmetic works ───────────────────────────
    r6, tr6 = small_company(small, limits=LIMITS)
    check(r6 is Result.APPLIES, f"₹2 crore / ₹30 crore is small ({r6})")
    check("SUPPLIED" in tr6.render(),
          "...and the trace records that the limits were supplied, not sourced")

    # Conjunctive: one limb over is enough to fail.
    big_turn = prof(paid_up_capital=Figure(Money.crore(2), "2024-25"),
                    turnover=Figure(Money.crore(50), "2024-25"))
    r7, tr7 = small_company(big_turn, limits=LIMITS)
    check(r7 is Result.DOES_NOT_APPLY,
          f"turnover over the limit fails, though capital passes ({r7})")
    check("exceeds" in tr7.render(), "...and the trace says which limb exceeded")

    big_cap = prof(paid_up_capital=Figure(Money.crore(9), "2024-25"),
                   turnover=Figure(Money.crore(1), "2024-25"))
    r8, _ = small_company(big_cap, limits=LIMITS)
    check(r8 is Result.DOES_NOT_APPLY, "capital over the limit fails too")

    # ── the asymmetry ───────────────────────────────────────────────────────
    unsure = CompanyProfile(
        company_class="private", incorporation_date=date(2019, 6, 1),
        as_of=date(2026, 8, 31), latest_financial_year="2024-25",
        paid_up_capital=Figure(Money.crore(2), "2024-25"),
        turnover=Figure(Money.crore(30), "2024-25"))       # exclusions all None
    r9, tr9 = small_company(unsure, limits=LIMITS)
    check(r9 is Result.INSUFFICIENT_DATA,
          f"relief is withheld while an exclusion is unknown ({r9})")
    check("relief" in tr9.render(), "...and the trace explains the asymmetry")

    # ...but an unknown exclusion does NOT block a definitive refusal.
    unsure_big = CompanyProfile(
        company_class="private", incorporation_date=date(2019, 6, 1),
        as_of=date(2026, 8, 31), latest_financial_year="2024-25",
        paid_up_capital=Figure(Money.crore(2), "2024-25"),
        turnover=Figure(Money.crore(50), "2024-25"))
    r10, _ = small_company(unsure_big, limits=LIMITS)
    check(r10 is Result.DOES_NOT_APPLY,
          "an unknown exclusion does not block a definitive 'not small'")

    # ── the financial year must match ───────────────────────────────────────
    wrong_year = prof(paid_up_capital=Figure(Money.crore(2), "2024-25"),
                      turnover=Figure(Money.crore(30), "2023-24"))
    r11, tr11 = small_company(wrong_year, limits=LIMITS)
    check(r11 is Result.INSUFFICIENT_DATA,
          f"a turnover from the wrong financial year is refused ({r11})")
    check("2023-24" in tr11.render(), "...and the trace names the mismatch")

    no_fy = CompanyProfile(company_class="private",
                           incorporation_date=date(2019, 6, 1),
                           as_of=date(2026, 8, 31),
                           is_holding_company=False, is_subsidiary_company=False,
                           is_section_8=False, governed_by_special_act=False)
    r12, tr12 = small_company(no_fy, limits=LIMITS)
    check(r12 is Result.INSUFFICIENT_DATA, "no financial year, no answer")
    check("financial year" in tr12.render(), "...and the trace says so")

    # ── a missing figure is distinguishable from a missing limit ────────────
    no_turn = prof(paid_up_capital=Figure(Money.crore(2), "2024-25"))
    _, tr13 = small_company(no_turn, limits=LIMITS)
    check("not on the profile" in tr13.render(),
          "a missing figure is reported as a missing figure")
    with _reg.stub_registration(None):      # no limits acquired: missing LIMIT
        _, tr14 = small_company(small)
    check("limit is not available" in tr14.render() or "not servable" in tr14.render(),
          "a missing limit is reported as a missing limit")

    # ── an OPC is a private company for this purpose ────────────────────────
    opc = prof(company_class="opc",
               paid_up_capital=Figure(Money.lakh(10), "2024-25"),
               turnover=Figure(Money.lakh(80), "2024-25"))
    r15, _ = small_company(opc, limits=LIMITS)
    check(r15 is Result.APPLIES, "an OPC is not a public company and can be small")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
