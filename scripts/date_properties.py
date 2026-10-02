#!/usr/bin/env python3
"""Thousands of seeded random dates over every DerivedDate rule, checking stated properties.

M4. `checker/derived_date.py` has worked examples in its own `_test()` -- 31 Mar + six months
is 30 Sep, dispatch 1 May + 21 clear days is 23 May. Worked examples prove the cases somebody
thought of. A deadline is arithmetic over the whole calendar, and the cases nobody thinks of
are leap days, month ends, year boundaries and the clamp.

So this states the rules as PROPERTIES and checks each over thousands of random (date,
interval) pairs from a fixed seed.

## Every rule in the module, and the property that pins it

    _add_months       the month lands exactly where modular arithmetic says, and the day is
                      min(anchor day, last day of that month) -- the clamp, stated rather
                      than inferred from 31 Mar + 6
    months/years      years are months x 12, exactly, for every anchor
    calendar days     result - anchor == value, to the day
    clear days        SS-2 1.2.6: exactly ONE day more than the same calendar count, because
                      the day of sending and the day of the Meeting are both excluded
    service addend    SS-1 1.3.6 / SS-2 1.2.6: +2 days for postal service, and ONLY for a
                      day-counted period whose source states the addend
    parse_interval    digits and number words agree; absent interval raises
    verify            the round trip reproduces for every derivation

## What a property buys over an example

`_add_months` composition is NOT associative under the clamp: 31 Jan +1 +1 is 28 Mar, while
31 Jan +2 is 31 Mar. That is correct -- each step clamps and information is lost -- and it is
the kind of thing an example-based test passes over in silence. It is asserted here as an
inequality rather than left to be discovered by a user with a January year-end.

## The harness proves it can fail

A property suite that cannot go red is worse than none, because it reports confidence it has
not earned. `--selftest` injects a deliberately wrong `_add_months` (off-by-one month, no
clamp) and requires the properties to CATCH it. If they do not, this exits nonzero.

Run: PYTHONPATH=. python3 scripts/date_properties.py
     PYTHONPATH=. python3 scripts/date_properties.py --test
"""
from __future__ import annotations

import calendar
import random
import sys
from datetime import date, timedelta

SEED = 20261002
N_DATES = 5_000           # random anchors per property
YEAR_LO, YEAR_HI = 1950, 2100
MONTHS = (0, 1, 2, 3, 6, 9, 12, 15, 18, 24, 36, 120)
DAYS = (1, 2, 7, 15, 21, 30, 45, 60, 90, 120)
POSTAL = ("post", "courier", "speed_post", "registered_post")
NON_POSTAL = ("hand", "electronic")

# Sources that STATE the interval, so `derive` has something to verify against. The interval
# must appear verbatim or the module raises, which is the whole point of its design.
SRC_DAYS = "shall be filed with the Registrar within {n} days of the date of the meeting"
SRC_CLEAR = ("Notice shall be given at least {n} clear days in advance of the Meeting. For "
             "the purpose of reckoning {n} days clear Notice, the day of sending the Notice "
             "and the day of Meeting shall not be counted. Further in case the company sends "
             "the Notice by post or courier, an additional two days shall be provided for "
             "the service of Notice.")
SRC_DAYS_ADDEND = (SRC_DAYS + ". In case the company sends the Notice by speed post or by "
                   "registered post, an additional two days shall be added for the service "
                   "of Notice.")
SRC_MONTHS = "within a period of {n} months from the date of closing of the financial year"


def _anchors(n: int, seed: int = SEED):
    rng = random.Random(seed)
    out = []
    while len(out) < n:
        y = rng.randint(YEAR_LO, YEAR_HI)
        m = rng.randint(1, 12)
        d = rng.randint(1, calendar.monthrange(y, m)[1])
        out.append(date(y, m, d))
    return out


def _last_day(y: int, m: int) -> int:
    return calendar.monthrange(y, m)[1]


# --- the properties -----------------------------------------------------------------------
# Each returns a list of failure strings. Empty means the property held on every sample.

def p_add_months_lands_exactly(dd, anchors) -> list[str]:
    """The month is modular arithmetic and the day is the clamp. Stated, not inferred."""
    bad = []
    for a in anchors:
        for n in MONTHS:
            got = dd._add_months(a, n)
            total = (a.year * 12 + (a.month - 1)) + n
            want_y, want_m = total // 12, total % 12 + 1
            want_d = min(a.day, _last_day(want_y, want_m))
            if (got.year, got.month, got.day) != (want_y, want_m, want_d):
                bad.append(f"{a} + {n}m -> {got}, expected {want_y}-{want_m:02d}-{want_d:02d}")
                if len(bad) > 5:
                    return bad
    return bad


def p_add_months_monotone(dd, anchors) -> list[str]:
    """More months is never an earlier date."""
    bad = []
    for a in anchors:
        prev = None
        for n in sorted(MONTHS):
            got = dd._add_months(a, n)
            if prev is not None and got < prev:
                bad.append(f"{a}: +{n}m went backwards ({got} < {prev})")
            prev = got
    return bad[:6]


def p_add_months_clamp_loses_information(dd, anchors) -> list[str]:
    """Stepwise addition can only land on or before one-shot addition.

    31 Jan +1 +1 = 28 Mar, 31 Jan +2 = 31 Mar. Each step clamps and the day cannot be
    recovered, so stepwise <= one-shot. An example-based test passes over this in silence.
    """
    bad = []
    for a in anchors:
        for x in (1, 2, 3, 6):
            for y in (1, 2, 5):
                step = dd._add_months(dd._add_months(a, x), y)
                shot = dd._add_months(a, x + y)
                if step > shot:
                    bad.append(f"{a}: (+{x})+{y} = {step} is AFTER +{x + y} = {shot}")
                    if len(bad) > 5:
                        return bad
    return bad


def p_add_months_day_never_invented(dd, anchors) -> list[str]:
    """The result's day is never greater than the anchor's, and is always a real date."""
    bad = []
    for a in anchors:
        for n in MONTHS:
            got = dd._add_months(a, n)
            if got.day > a.day:
                bad.append(f"{a} + {n}m -> {got}: day grew, which the clamp forbids")
            if got.day > _last_day(got.year, got.month):
                bad.append(f"{a} + {n}m -> {got}: not a real date")
    return bad[:6]


def p_years_are_months_times_twelve(dd, anchors) -> list[str]:
    """`derive` routes years through _add_months(value * 12). Exactly, for every anchor."""
    bad = []
    for a in anchors:
        for y in (1, 2, 3, 10):
            got = dd.derive(anchor=a, anchor_label="x", citation="c",
                            source_text=f"within {y} years of the said date").result
            if got != dd._add_months(a, y * 12):
                bad.append(f"{a} + {y}y -> {got}, != +{y * 12}m {dd._add_months(a, y * 12)}")
    return bad[:6]


def p_calendar_days_exact(dd, anchors) -> list[str]:
    """result - anchor == value, to the day, with no month or leap-year interference."""
    bad = []
    for a in anchors:
        for n in DAYS:
            got = dd.derive(anchor=a, anchor_label="x", citation="c",
                            source_text=SRC_DAYS.format(n=n)).result
            if (got - a).days != n:
                bad.append(f"{a} + {n}d -> {got}: delta {(got - a).days}, expected {n}")
                if len(bad) > 5:
                    return bad
    return bad


def p_clear_days_is_one_more(dd, anchors) -> list[str]:
    """SS-2 1.2.6: the day of sending and the day of the Meeting are BOTH excluded.

    So a clear count is exactly one day beyond the same calendar count -- never two, never
    the same. Both excluded days are at the ends of a span of `value` clear days between them.
    """
    bad = []
    for a in anchors:
        for n in DAYS:
            cal = dd.derive(anchor=a, anchor_label="x", citation="c",
                            source_text=SRC_DAYS.format(n=n)).result
            clear = dd.derive(anchor=a, anchor_label="x", citation="c",
                              source_text=SRC_CLEAR.format(n=n), service_mode="hand").result
            if (clear - cal).days != 1:
                bad.append(f"{a}, {n}d: clear {clear} vs calendar {cal}, "
                           f"differ by {(clear - cal).days}, expected 1")
                if len(bad) > 5:
                    return bad
    return bad


def p_clear_flag_from_source_not_argument(dd, anchors) -> list[str]:
    """A source saying "clear days" forces clear counting even when the caller said calendar.

    The source is the authority, not the call site. `derive` overrides `day_count` when the
    provision says "clear", and this holds it to that.
    """
    bad = []
    for a in anchors[:400]:
        for n in (7, 21):
            dr = dd.derive(anchor=a, anchor_label="x", citation="c",
                           source_text=SRC_CLEAR.format(n=n), day_count="calendar")
            if dr.day_count != "clear" or (dr.result - a).days != n + 1:
                bad.append(f"{a}, {n} clear days: day_count={dr.day_count}, "
                           f"delta={(dr.result - a).days}")
    return bad[:6]


def p_service_addend_only_where_earned(dd, anchors) -> list[str]:
    """+2 for postal service, and ONLY for a day period whose source states the addend.

    Three ways it must NOT apply: a non-postal mode, a source that never mentions the
    addend, and a month or year interval. The last matters most -- a postal notice with a
    six-month period must not silently gain two days.
    """
    bad = []
    for a in anchors[:600]:
        # postal + days + source states it -> exactly +2 over hand delivery
        for mode in POSTAL:
            hand = dd.derive(anchor=a, anchor_label="x", citation="c",
                             source_text=SRC_DAYS_ADDEND.format(n=30),
                             service_mode="hand")
            post = dd.derive(anchor=a, anchor_label="x", citation="c",
                             source_text=SRC_DAYS_ADDEND.format(n=30),
                             service_mode=mode)
            if post.service_addend != 2 or (post.result - hand.result).days != 2:
                bad.append(f"{a} {mode}: addend {post.service_addend}, "
                           f"delta {(post.result - hand.result).days}, expected 2")

        # non-postal never gets it
        for mode in NON_POSTAL:
            dr = dd.derive(anchor=a, anchor_label="x", citation="c",
                           source_text=SRC_DAYS_ADDEND.format(n=30), service_mode=mode)
            if dr.service_addend != 0:
                bad.append(f"{a} {mode}: got addend {dr.service_addend}, must be 0")

        # a source that never states the addend never gets it, however it is served
        for mode in POSTAL:
            dr = dd.derive(anchor=a, anchor_label="x", citation="c",
                           source_text=SRC_DAYS.format(n=30), service_mode=mode)
            if dr.service_addend != 0:
                bad.append(f"{a} {mode}, silent source: addend {dr.service_addend}, must be 0")

        # a MONTH period never gets a day addend, even by post
        for mode in POSTAL:
            dr = dd.derive(anchor=a, anchor_label="x", citation="c",
                           source_text=SRC_MONTHS.format(n=6) +
                           " an additional two days shall be provided",
                           service_mode=mode)
            if dr.service_addend != 0 or dr.result != dd._add_months(a, 6):
                bad.append(f"{a} {mode}, 6 months: addend {dr.service_addend}, "
                           f"result {dr.result} != {dd._add_months(a, 6)}")
        if len(bad) > 5:
            return bad[:6]
    return bad


def p_words_and_digits_agree(dd, anchors) -> list[str]:
    """"thirty days" and "30 days" are the same interval, so they derive the same date."""
    words = {1: "one", 2: "two", 7: "seven", 15: "fifteen", 21: "twenty-one", 30: "thirty",
             45: "forty-five", 60: "sixty", 90: "ninety", 120: "one hundred and twenty"}
    bad = []
    for a in anchors[:800]:
        for n, w in words.items():
            d1 = dd.derive(anchor=a, anchor_label="x", citation="c",
                           source_text=SRC_DAYS.format(n=n)).result
            d2 = dd.derive(anchor=a, anchor_label="x", citation="c",
                           source_text=SRC_DAYS.format(n=w)).result
            if d1 != d2:
                bad.append(f"{a}: {n} -> {d1} but {w!r} -> {d2}")
                if len(bad) > 5:
                    return bad
    return bad


def p_verify_round_trips(dd, anchors) -> list[str]:
    """Every derivation re-verifies against the source it came from."""
    bad = []
    for a in anchors[:800]:
        for src, mode in ((SRC_DAYS.format(n=30), "hand"),
                          (SRC_CLEAR.format(n=21), "hand"),
                          (SRC_DAYS_ADDEND.format(n=7), "speed_post"),
                          (SRC_MONTHS.format(n=6), "hand")):
            got = dd.derive(anchor=a, anchor_label="x", citation="c",
                            source_text=src, service_mode=mode)
            if not dd.verify(got, src):
                bad.append(f"{a}: derivation from {src[:40]!r} failed its own verify")
                if len(bad) > 5:
                    return bad
    return bad


def p_verify_rejects_a_changed_source(dd, anchors) -> list[str]:
    """A derivation does NOT verify against a source whose interval differs.

    The negative half. Without it `verify` returning True unconditionally would pass the
    property above, and the round trip would prove nothing.
    """
    bad = []
    for a in anchors[:400]:
        got = dd.derive(anchor=a, anchor_label="x", citation="c",
                        source_text=SRC_DAYS.format(n=30))
        if dd.verify(got, SRC_DAYS.format(n=45)):
            bad.append(f"{a}: a 30-day derivation verified against a 45-day source")
        if dd.verify(got, "this provision states no interval at all"):
            bad.append(f"{a}: verified against a source with no interval")
    return bad[:6]


def p_absent_interval_raises(dd, anchors) -> list[str]:
    """No interval in the provision means abstain, never a guessed deadline."""
    bad = []
    for text in ("The Board shall meet as often as necessary.",
                 "A company shall keep its register at the registered office.",
                 "", "   "):
        try:
            dd.derive(anchor=date(2026, 3, 31), anchor_label="x", citation="c",
                      source_text=text)
            bad.append(f"no interval in {text[:40]!r} but derive returned a date")
        except dd.IntervalNotInSource:
            pass
    return bad


PROPERTIES = (
    ("_add_months lands exactly where modular arithmetic says", p_add_months_lands_exactly),
    ("_add_months is monotone in the number of months", p_add_months_monotone),
    ("the clamp loses information, so stepwise <= one-shot", p_add_months_clamp_loses_information),
    ("_add_months never invents a day, and always returns a real date",
     p_add_months_day_never_invented),
    ("years are months x 12, exactly", p_years_are_months_times_twelve),
    ("a calendar day count is exact to the day", p_calendar_days_exact),
    ("a clear day count is exactly ONE day beyond the calendar count", p_clear_days_is_one_more),
    ("the source decides clear counting, not the caller", p_clear_flag_from_source_not_argument),
    ("the +2 service addend applies only where it is earned",
     p_service_addend_only_where_earned),
    ("number words and digits derive the same date", p_words_and_digits_agree),
    ("every derivation re-verifies against its own source", p_verify_round_trips),
    ("...and does NOT verify against a changed source", p_verify_rejects_a_changed_source),
    ("a provision stating no interval raises rather than guessing", p_absent_interval_raises),
)


def run(module=None, *, n: int = N_DATES, seed: int = SEED) -> dict:
    import checker.derived_date as real
    dd = module or real
    anchors = _anchors(n, seed)
    results = []
    for label, fn in PROPERTIES:
        failures = fn(dd, anchors)
        results.append({"property": label, "failures": failures,
                        "held": not failures})
    return {"anchors": len(anchors), "seed": seed,
            "years": [YEAR_LO, YEAR_HI],
            "properties": results,
            "broken": [r["property"] for r in results if not r["held"]]}


# --- the harness must be able to fail -----------------------------------------------------
# A property suite that cannot go red reports confidence it has not earned. Each mutant below
# breaks ONE rule, and the run must catch every one. This is the check that makes the thirteen
# HELDs above evidence rather than decoration.

def _mutants():
    """(name, patch) pairs. `patch` mutates the module in place and returns an undo thunk."""
    import checker.derived_date as dd

    def off_by_one_month():
        real = dd._add_months
        dd._add_months = lambda d, n: real(d, n + 1)
        return lambda: setattr(dd, "_add_months", real)

    def no_clamp():
        real = dd._add_months

        def naive(d, n):
            total = (d.year * 12 + (d.month - 1)) + n
            y, m = total // 12, total % 12 + 1
            # The bug: keep the anchor's day, falling back to the 1st when it does not exist.
            # 31 Jan + 1 becomes 1 Feb instead of 28 Feb.
            try:
                return date(y, m, d.day)
            except ValueError:
                return date(y, m, 1)
        dd._add_months = naive
        return lambda: setattr(dd, "_add_months", real)

    def clear_count_not_excluded():
        real = dd.derive

        def shifted(**kw):
            got = real(**kw)
            if got.day_count == "clear":
                object.__setattr__(got, "result", got.result - timedelta(days=1))
            return got
        dd.derive = shifted
        return lambda: setattr(dd, "derive", real)

    def addend_three_days():
        real = dd.SERVICE_ADDEND_DAYS
        dd.SERVICE_ADDEND_DAYS = 3
        return lambda: setattr(dd, "SERVICE_ADDEND_DAYS", real)

    def addend_on_every_mode():
        real = dd._POSTAL
        dd._POSTAL = frozenset(real | {"hand", "electronic"})
        return lambda: setattr(dd, "_POSTAL", real)

    def word_numbers_wrong():
        real = dict(dd._WORD_NUM)

        def undo():
            dd._WORD_NUM.clear()
            dd._WORD_NUM.update(real)
        dd._WORD_NUM["thirty"] = 31
        return undo

    def verify_always_true():
        real = dd.verify
        dd.verify = lambda d, s: True
        return lambda: setattr(dd, "verify", real)

    def never_raises():
        real = dd.parse_interval
        dd.parse_interval = lambda s: (
            real(s) if dd._INTERVAL.search(s) else ("thirty days", 30, "day", False))
        return lambda: setattr(dd, "parse_interval", real)

    return (("_add_months off by one month", off_by_one_month),
            ("_add_months with no month-end clamp", no_clamp),
            ("clear days not excluding both ends", clear_count_not_excluded),
            ("service addend of 3 days instead of 2", addend_three_days),
            ("service addend applied to hand delivery", addend_on_every_mode),
            ("the word 'thirty' parsed as 31", word_numbers_wrong),
            ("verify() returning True unconditionally", verify_always_true),
            ("a missing interval defaulting to thirty days", never_raises))


def selftest(*, n: int = 300) -> dict:
    """Break each rule in turn and require the properties to notice."""
    out = []
    for name, patch in _mutants():
        undo = patch()
        try:
            r = run(n=n)
        finally:
            undo()
        out.append({"mutant": name, "caught_by": r["broken"], "caught": bool(r["broken"])})
    return {"mutants": out, "missed": [m["mutant"] for m in out if not m["caught"]]}


def report(r: dict, sr: dict | None = None) -> str:
    lines = [f"  {r['anchors']} random anchors, {r['years'][0]}-{r['years'][1]}, "
             f"seed {r['seed']}", ""]
    for p in r["properties"]:
        lines.append(f"    {'HELD' if p['held'] else 'BROKE'}  {p['property']}")
        for f in p["failures"][:3]:
            lines.append(f"            {f}")
    if sr:
        lines += ["", "  the harness proves it can fail:"]
        for m in sr["mutants"]:
            mark = "caught" if m["caught"] else "MISSED"
            lines.append(f"    {mark:<7} {m['mutant']}")
            if m["caught"]:
                lines.append(f"            by: {m['caught_by'][0]}")
        if sr["missed"]:
            lines.append(f"\n  {len(sr['missed'])} mutant(s) NOT caught -- those rules are "
                         f"unmeasured, whatever the HELDs above say.")
    return "\n".join(lines)


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

    print("date_properties")

    r = run(n=600)
    check(r["anchors"] == 600, f"random anchors are drawn ({r['anchors']})")
    check(len(r["properties"]) == len(PROPERTIES) >= 13,
          f"every property runs ({len(r['properties'])})")
    for p in r["properties"]:
        check(p["held"], f"{p['property']} ({p['failures'][:1]})")

    # ── the harness must be able to fail ───────────────────────────────────
    sr = selftest(n=120)
    for m in sr["mutants"]:
        check(m["caught"], f"a broken rule IS caught: {m['mutant']} "
                           f"({m['caught_by'][:1] if m['caught'] else 'MISSED'})")
    check(not sr["missed"],
          f"every mutant is caught, so the HELDs above are evidence ({sr['missed']})")

    # ── the module is left exactly as it was found ─────────────────────────
    import checker.derived_date as dd
    check(dd.SERVICE_ADDEND_DAYS == 2 and dd._WORD_NUM["thirty"] == 30
          and "hand" not in dd._POSTAL,
          "the mutants are undone -- a self-test that leaves the module patched would "
          "poison every suite that runs after it")
    check(dd.derive(anchor=date(2026, 3, 31), anchor_label="FY close", citation="s.96",
                    source_text=SRC_MONTHS.format(n=6)).result == date(2026, 9, 30),
          "...checked by re-deriving the module's own worked example, 31 Mar + 6m = 30 Sep")

    # ── seeded means reproducible ──────────────────────────────────────────
    check(_anchors(50) == _anchors(50) and _anchors(50) != _anchors(50, seed=1),
          "the anchors are seeded: reproducible, and the seed actually varies them")

    text = report(r, sr)
    check("HELD" in text and "caught" in text, "the report shows both halves")
    check("accuracy" not in text.lower(), "...and claims no accuracy")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    if "--test" in sys.argv:
        raise SystemExit(_test())
    res = run()
    # The mutation check always runs. It is not an optional extra: without it the thirteen
    # HELDs are a claim about this harness, not about the module.
    sres = selftest()
    print(report(res, sres))
    raise SystemExit(1 if res["broken"] or sres["missed"] else 0)
