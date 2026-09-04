#!/usr/bin/env python3
"""The Section 173 vertical slice, end to end. Board meetings for one company-year.

`checker/s173_slice.py` has been built and passing for some time with no way to
run it, so the capability existed and could not be shown to anybody. That is the
gap this closes: the review engine was already here, the demo was not.

The point of the walk is the same as the s.96 slice — answer a company
secretary's first question, "how do you know that?", with the working rather
than with confidence. Nothing here calls a language model. Every value comes
from a provision, a date the user supplied, or arithmetic on the two.

## Why the interesting case is the one that refuses

Three companies are walked. The third holds four meetings, none more than 120
days apart, and still does not come back COMPLIANT — because s.174 quorum is a
separate question this slice does not answer, and a board that met four times
with two directors present out of nine was inquorate every time. A tool that
said COMPLIANT there would be telling a director their year was fine when it was
not. The slice surfaces the question instead of assuming it away.

The second is the regime trap: the relaxed s.173(5) regime turns on small-company
status, and small-company status currently REFUSES for want of G.S.R. 700(E)
(task S-002). So a company that is probably small cannot be given the relaxed
regime, and the walk shows that refusal propagating rather than hiding it.

Run: python3 scripts/slice_s173.py            (walk the slice)
     python3 scripts/slice_s173.py --test     (assert it end to end)
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from applicability import Result                              # noqa: E402
from checker.classify import small_company                    # noqa: E402
from checker.company_profile import CompanyProfile, Figure, Money  # noqa: E402
from checker.s173_slice import (COMPLIANT, INDETERMINATE, NOT_COMPLIANT,  # noqa: E402
                                review)


def regime_for(profile: CompanyProfile) -> tuple[str, str]:
    """Which s.173 regime applies, and why. Refuses rather than guessing.

    s.173(5) relaxes the requirement for a small company, so the regime depends
    on a classification that is itself blocked. Returning "standard" on an
    unresolved classification would be a guess dressed as a default, and it
    guesses in the direction that imposes MORE obligations — safer for us,
    wrong for the user, who would be told to hold meetings they may not owe.
    """
    verdict, trace = small_company(profile)
    if verdict is Result.APPLIES:
        return "small_company", "classified small under s.2(85)"
    if verdict is Result.DOES_NOT_APPLY:
        return "other", "not a small company under s.2(85)"
    return "UNRESOLVED", trace.detail


def walk(label: str, profile: CompanyProfile, year: int, meetings: list[date],
         *, total_board_strength: int | None = None,
         incorporation_date: date | None = None) -> None:
    print("\n" + "=" * 72)
    print(f"MATTER: {label}")
    print("=" * 72)

    cls, why = regime_for(profile)
    print(f"  company class   : {cls}")
    print(f"  basis           : {why[:180]}")

    if cls == "UNRESOLVED":
        print("\n  The s.173 regime turns on small-company status, and that")
        print("  classification refuses. The review below therefore runs on the")
        print("  STANDARD regime, and its result is provisional: if the company")
        print("  is in fact small, the relaxed s.173(5) regime applies instead.")
        cls_for_review = "other"
    else:
        cls_for_review = cls

    r = review(company_class=cls_for_review, calendar_year=year, meetings=meetings,
               incorporation_date=incorporation_date,
               total_board_strength=total_board_strength)
    print(r.render())
    if cls == "UNRESOLVED":
        print("  PROVISIONAL — regime unconfirmed, see S-002")


def main() -> None:
    print(__doc__.split("Run:")[0].strip())

    common = dict(incorporation_date=date(2019, 6, 1), as_of=date(2026, 8, 31),
                  latest_financial_year="2024-25", is_holding_company=False,
                  is_subsidiary_company=False, is_section_8=False,
                  governed_by_special_act=False)

    # 1. A public company that plainly is not small — the classification is
    #    definitive without any threshold, so the regime is settled.
    walk("Public company, four meetings, widest gap 118 days",
         CompanyProfile(company_class="public", **common),
         2025, [date(2025, 2, 10), date(2025, 6, 5),
                date(2025, 9, 30), date(2025, 12, 20)],
         total_board_strength=7)

    # 2. A private company whose figures are under the commonly-cited limits —
    #    and whose regime cannot be settled, because the limits are unacquired.
    walk("Private company, figures under the cited limits, three meetings",
         CompanyProfile(company_class="private",
                        paid_up_capital=Figure(Money.crore(2), "2024-25"),
                        turnover=Figure(Money.crore(30), "2024-25"), **common),
         2025, [date(2025, 3, 1), date(2025, 7, 20), date(2025, 11, 15)],
         total_board_strength=4)

    # 3. Four meetings, every gap inside the ceiling — and still not COMPLIANT.
    walk("Public company, four meetings, board of nine, attendance unknown",
         CompanyProfile(company_class="public", **common),
         2025, [date(2025, 1, 15), date(2025, 4, 20),
                date(2025, 8, 1), date(2025, 11, 10)],
         total_board_strength=9)

    print("\n" + "=" * 72)
    print("Nothing above consulted a language model.")
    print("Every date was supplied; every limit came from s.173; every verdict")
    print("is arithmetic on the two, and every refusal names what is missing.")
    print("=" * 72)


def _test() -> int:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    print("slice_s173")
    common = dict(incorporation_date=date(2019, 6, 1), as_of=date(2026, 8, 31),
                  latest_financial_year="2024-25", is_holding_company=False,
                  is_subsidiary_company=False, is_section_8=False,
                  governed_by_special_act=False)

    # A public company needs no threshold to be classified.
    cls, why = regime_for(CompanyProfile(company_class="public", **common))
    check(cls == "other", f"a public company resolves without a threshold ({cls})")
    check("not a small company" in why, f"...and says why ({why[:50]})")

    # A private company under the cited limits cannot be classified while the
    # Rule is unacquired. Forced via the stub so this demonstrates the blocked
    # behaviour deterministically, independent of the live 700(E) attestation.
    import importlib
    _reg = importlib.import_module("scripts.register_gsr700e")
    p = CompanyProfile(company_class="private",
                       paid_up_capital=Figure(Money.crore(2), "2024-25"),
                       turnover=Figure(Money.crore(30), "2024-25"), **common)
    with _reg.stub_registration(None):
        cls2, why2 = regime_for(p)
    check(cls2 == "UNRESOLVED",
          f"the regime refuses while G.S.R. 700(E) is unacquired ({cls2})")
    check("servable" in why2 or "S-002" in why2,
          f"...naming the acquisition gap ({why2[:70]})")
    # ...and resolves once the Rule is attested.
    with _reg.stub_registration(_reg.attested_stub()):
        cls3, _ = regime_for(p)
    check(cls3 != "UNRESOLVED",
          f"the regime resolves once 700(E) is attested ({cls3})")

    # The refusal must NOT silently become the standard regime in the result.
    # It propagates as a provisional answer, which is a different claim.
    r = review(company_class="other", calendar_year=2025,
               meetings=[date(2025, 3, 1), date(2025, 7, 20), date(2025, 11, 15)])
    check(r.status in (NOT_COMPLIANT, INDETERMINATE),
          f"three meetings do not satisfy the standard regime ({r.status})")

    # Four well-spaced meetings, and still not a clean COMPLIANT, because
    # quorum is a separate question this slice does not answer.
    r2 = review(company_class="other", calendar_year=2025,
                meetings=[date(2025, 1, 15), date(2025, 4, 20),
                          date(2025, 8, 1), date(2025, 11, 10)],
                total_board_strength=9)
    check(r2.status != COMPLIANT,
          f"four spaced meetings alone do not earn COMPLIANT ({r2.status})")
    check(bool(r2.open_questions or r2.missing_facts),
          "...and the card names what is still open")

    # The walk must run without raising.
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    with _reg.stub_registration(None), redirect_stdout(buf):
        main()
    out = buf.getvalue()
    check("MATTER:" in out and out.count("MATTER:") == 3,
          f"the walk runs three matters ({out.count('MATTER:')})")
    check("PROVISIONAL" in out,
          "the unresolved regime is marked provisional in the walk")
    check("Nothing above consulted a language model." in out,
          "the walk states that no model was consulted")
    check("S-002" in out, "...and points at the task that would unblock it")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--test":
        raise SystemExit(_test())
    main()
