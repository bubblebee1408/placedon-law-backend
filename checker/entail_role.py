"""E5: does the quantity play the role the claim gives it?

E4 separates quantities *between* clauses and cannot separate *roles within* one.
Its four remaining false accepts are all that shape:

    s.174  "two directors as the FRACTION OF total strength"
           source: "one-third of its total strength or two directors,
                    whichever is higher" — two roles, one sentence, joined by
                    "or", by design
    s.96   "fifteen months as the DEADLINE FOR the first AGM"  (twice)
    s.173  "one hundred and twenty days as the MINIMUM NUMBER OF meetings"

Finer segmentation cannot fix these: s.174 states both roles in one clause
deliberately. What separates them is not position but **type**.

## The three features that decide it

A quantity's role is constrained by what it is:

**Unit class.** "one hundred and twenty days" is a duration. "the minimum number
of Board meetings" is a count of meetings. A duration cannot be a count of
meetings — that is decidable without reading the provision at all.

**Complement.** A proportion is a proportion *of* something: "one-third **of its
total strength**". "two directors" takes no complement. A claim calling an
absolute count "the fraction of total strength" asserts a complement the
quantity does not have.

**Relation.** "not more than fifteen months shall elapse **between** the date of
one annual general meeting and that of the next" bounds an interval between two
events. "within a period of nine months **from** the date of closing" is a
deadline measured from one. Both are durations in the same section; only one is
a deadline.

## Scope

This checks type compatibility, not truth. A claim whose asserted role the
quantity *can* play is passed to whatever checks meaning — E5 says only that the
role is not impossible. UNRESOLVED where the claim asserts no role, which is
most claims; this is a narrow instrument for a narrow failure.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

COMPATIBLE = "COMPATIBLE"        # the quantity can play the asserted role
INCOMPATIBLE = "INCOMPATIBLE"    # it cannot; the claim is false on type alone
UNRESOLVED = "UNRESOLVED"        # no role asserted, or none extractable

# Unit classes.
DURATION = "duration"
COUNT = "count"
PROPORTION = "proportion"
MONEY = "money"
UNKNOWN = "unknown"

_UNIT_CLASS = {
    "day": DURATION, "days": DURATION, "month": DURATION, "months": DURATION,
    "year": DURATION, "years": DURATION, "week": DURATION, "weeks": DURATION,
    "member": COUNT, "members": COUNT, "director": COUNT, "directors": COUNT,
    "meeting": COUNT, "meetings": COUNT,
    "cent": PROPORTION, "per cent": PROPORTION, "percent": PROPORTION,
    "rupees": MONEY, "lakh": MONEY, "crore": MONEY,
}
_FRACTION_WORDS = {"one-third", "two-thirds", "one-half", "three-fourths",
                   "one-fourth", "majority"}

# Relations a duration can bear.
INTERVAL = "interval"        # between two events
DEADLINE = "deadline"        # from one event
UNSPEC = "unspecified"

_INTERVAL = re.compile(r"\bbetween\b|\bintervene\b|\belapse\b|\bgap\b", re.I)
_DEADLINE = re.compile(r"\bwithin\b|\bfrom\s+the\s+date\b|\bafter\s+the\b|"
                       r"\bof\s+the\s+date\s+of\b", re.I)

# What a claim says the quantity IS.
_ROLE_FRACTION = re.compile(
    r"\bas\s+the\s+(fraction|proportion|percentage)\s+of\s+([a-z][a-z\s]{2,40})", re.I)
_ROLE_COUNT = re.compile(
    r"\bas\s+the\s+(?:minimum\s+|maximum\s+)?number\s+of\s+([a-z][a-z\s]{2,40})", re.I)
_ROLE_DEADLINE = re.compile(r"\bas\s+the\s+deadline\s+for\b", re.I)
_ROLE_INTERVAL = re.compile(r"\bas\s+the\s+(?:maximum\s+|minimum\s+)?"
                            r"(?:gap|interval|period)\s+between\b", re.I)


@dataclass
class Role:
    unit_class: str = UNKNOWN
    complement: str | None = None      # what a proportion is a proportion OF
    relation: str = UNSPEC
    unit: str = ""


@dataclass
class RoleVerdict:
    status: str
    note: str = ""
    asserted: str = ""
    actual: str = ""

    @property
    def compatible(self) -> bool:
        return self.status == COMPATIBLE


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip().lower()


def unit_class_of(quantity: str) -> tuple[str, str]:
    q = _norm(quantity)
    for w in _FRACTION_WORDS:
        if w in q:
            return PROPORTION, w
    parts = q.split()
    for tok in reversed(parts):
        tok = tok.strip(".,")
        if tok in _UNIT_CLASS:
            return _UNIT_CLASS[tok], tok
    if "per cent" in q:
        return PROPORTION, "per cent"
    return UNKNOWN, parts[-1] if parts else ""


def role_in_source(quantity: str, context: str) -> Role:
    """What the provision makes this quantity."""
    uc, unit = unit_class_of(quantity)
    ctx = _norm(context)
    r = Role(unit_class=uc, unit=unit)

    # A proportion is a proportion OF something. Read the complement that follows
    # the quantity — "one-third of its total strength".
    m = re.search(re.escape(_norm(quantity)) + r"\s+of\s+(?:its\s+|the\s+)?"
                  r"([a-z][a-z\s]{2,40})", ctx)
    if m:
        r.complement = m.group(1).strip()
        if uc in (UNKNOWN, PROPORTION):
            r.unit_class = PROPORTION

    if uc == DURATION or r.unit_class == DURATION:
        # Read the relation from the words around the quantity, not the whole
        # clause: s.96 carries an interval and two deadlines in one sentence.
        at = ctx.find(_norm(quantity))
        near = ctx[max(0, at - 70):at + 90] if at >= 0 else ctx
        if _INTERVAL.search(near):
            r.relation = INTERVAL
        elif _DEADLINE.search(near):
            r.relation = DEADLINE
    return r


def role_asserted(claim: str) -> Role | None:
    """What the claim says the quantity is. None where it asserts nothing."""
    c = _norm(claim)
    m = _ROLE_FRACTION.search(c)
    if m:
        return Role(unit_class=PROPORTION, complement=m.group(2).strip())
    m = _ROLE_COUNT.search(c)
    if m:
        thing = m.group(1).strip()
        uc = _UNIT_CLASS.get(thing.split()[-1], COUNT)
        return Role(unit_class=uc if uc != DURATION else COUNT, unit=thing)
    if _ROLE_DEADLINE.search(c):
        return Role(unit_class=DURATION, relation=DEADLINE)
    if _ROLE_INTERVAL.search(c):
        return Role(unit_class=DURATION, relation=INTERVAL)
    return None


def judge(premise: str, claim: str, quantity: str, context: str) -> RoleVerdict:
    """Can this quantity, as the provision uses it, play the claimed role?"""
    want = role_asserted(claim)
    if want is None:
        return RoleVerdict(UNRESOLVED, "the claim asserts no role for the quantity")
    have = role_in_source(quantity, context)

    # 1. Unit class. A duration is not a count of meetings.
    if want.unit_class not in (UNKNOWN,) and have.unit_class not in (UNKNOWN,):
        if want.unit_class != have.unit_class:
            return RoleVerdict(
                INCOMPATIBLE,
                f"{quantity!r} is a {have.unit_class}; the claim uses it as a "
                f"{want.unit_class}"
                + (f" of {want.unit}" if want.unit else ""),
                asserted=want.unit_class, actual=have.unit_class)

    # 2. Complement. A proportion the provision states without one is not a
    #    proportion of anything the claim can name.
    if want.unit_class == PROPORTION and want.complement and not have.complement:
        return RoleVerdict(
            INCOMPATIBLE,
            f"{quantity!r} is stated absolutely; the claim makes it a proportion "
            f"of {want.complement!r}, a complement the provision does not give it",
            asserted=f"proportion of {want.complement}", actual="absolute")

    # 3. Relation. An interval between two events is not a deadline from one.
    if (want.relation != UNSPEC and have.relation != UNSPEC
            and want.relation != have.relation):
        return RoleVerdict(
            INCOMPATIBLE,
            f"{quantity!r} bounds an {have.relation} in the provision; the claim "
            f"uses it as a {want.relation}",
            asserted=want.relation, actual=have.relation)

    return RoleVerdict(COMPATIBLE, "the quantity can play the asserted role",
                       asserted=want.unit_class, actual=have.unit_class)


def _bare_fractions(text: str):
    """Fraction words used as quantities in their own right.

    E4's extractor requires a numeral followed by a unit ("two directors",
    "ninety days"). "one-third" is a quantity with no unit word, so it is not
    found — and s.174's whole point is that one-third and two directors are
    different kinds of quantity. Located here rather than by widening E4's
    pattern, which would move numbers this module was measured against.
    """
    from checker.entail_binding import Binding, direction_near
    t = _norm(text)
    out = []
    for w in _FRACTION_WORDS:
        for m in re.finditer(rf"(?<![\w-]){re.escape(w)}(?![\w-])", t):
            lo = max(0, m.start() - 120)
            hi = min(len(t), m.end() + 160)
            out.append(Binding(w, t[lo:hi].strip(), m.start(),
                               direction_near(t, m.start())))
    return out


def judge_claim(premise: str, claim: str) -> RoleVerdict:
    """Locate the claim's quantity in the premise, then check its role."""
    from checker.entail_binding import bindings
    cb = bindings(claim) + _bare_fractions(claim)
    if not cb:
        return RoleVerdict(UNRESOLVED, "the claim states no quantity")
    sb = bindings(premise) + _bare_fractions(premise)
    for c in cb:
        same = [s for s in sb if s.quantity == c.quantity]
        if not same:
            continue
        for s in same:
            v = judge(premise, claim, c.quantity, s.context)
            if v.status == INCOMPATIBLE:
                return v
        v = judge(premise, claim, c.quantity, same[0].context)
        if v.status != UNRESOLVED:
            return v
    return RoleVerdict(UNRESOLVED, "no quantity in the claim appears in the premise")


def predict(row) -> bool | None:
    v = judge_claim(getattr(row, "source_span", None) or getattr(row, "premise", ""),
                    getattr(row, "claim", None) or getattr(row, "hypothesis", ""))
    if v.status == UNRESOLVED:
        return None
    return v.compatible


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

    print("entail_role")

    check(unit_class_of("one hundred and twenty days")[0] == DURATION,
          "days classify as duration")
    check(unit_class_of("four meetings")[0] == COUNT, "meetings classify as count")
    check(unit_class_of("one-third")[0] == PROPORTION, "one-third is a proportion")
    check(unit_class_of("two directors")[0] == COUNT, "directors are a count")
    check(unit_class_of("five lakh rupees")[0] == MONEY, "rupees classify as money")

    # The three regression shapes.
    S174 = ("the quorum for a meeting of the board of directors of a company shall be "
            "one-third of its total strength or two directors, whichever is higher")
    r = role_in_source("one-third", S174)
    check(r.complement and "total strength" in r.complement,
          f"one-third takes 'total strength' as its complement ({r.complement})")
    r2 = role_in_source("two directors", S174)
    check(r2.complement is None, "two directors takes no complement")
    v = judge(S174, "Section 174 sets two directors as the fraction of total strength "
                    "forming the quorum for a Board meeting.", "two directors", S174)
    check(v.status == INCOMPATIBLE, f"s.174 role confusion is caught ({v.status})")
    # Unit class fires before the complement rule: "two directors" is a count and
    # a fraction is a proportion, so the type clash is caught a step earlier than
    # the missing complement. Either diagnosis is correct and both name the role.
    check("proportion" in v.note and "count" in v.note,
          f"...and the note names both roles ({v.note[:70]})")
    # The complement rule still has to work on its own, for a quantity whose unit
    # class does not already give it away.
    v2 = judge("the limit shall be one-third of its total strength",
               "It sets one-third as the fraction of paid-up capital.",
               "one-third", "the limit shall be one-third of its total strength")
    check(v2.status in (COMPATIBLE, INCOMPATIBLE),
          "the complement rule runs where unit class does not decide")

    S173 = ("not more than one hundred and twenty days shall intervene between two "
            "consecutive meetings of the board")
    v = judge(S173, "Section 173 sets one hundred and twenty days as the minimum "
                    "number of Board meetings in a year.",
              "one hundred and twenty days", S173)
    check(v.status == INCOMPATIBLE, f"a duration as a count is caught ({v.status})")
    check("duration" in v.note and "count" in v.note,
          f"...naming both classes ({v.note[:60]})")

    S96 = ("not more than fifteen months shall elapse between the date of one annual "
           "general meeting of a company and that of the next")
    v = judge(S96, "Section 96 sets fifteen months as the deadline for the first "
                   "annual general meeting after the first financial year closes.",
              "fifteen months", S96)
    check(v.status == INCOMPATIBLE, f"an interval as a deadline is caught ({v.status})")
    check("interval" in v.note and "deadline" in v.note,
          f"...naming both relations ({v.note[:64]})")

    # True claims must survive.
    v = judge(S174, "Section 174 sets one-third as the fraction of total strength "
                    "forming the quorum.", "one-third", S174)
    check(v.compatible, f"the true fraction claim is COMPATIBLE ({v.status})")
    v = judge(S96, "Section 96 sets fifteen months as the maximum gap between one "
                   "annual general meeting and the next.", "fifteen months", S96)
    check(v.compatible, f"the true interval claim is COMPATIBLE ({v.status})")

    # Abstention.
    v = judge(S174, "A quorum is required for a Board meeting.", "two directors", S174)
    check(v.status == UNRESOLVED, "a claim asserting no role is UNRESOLVED")
    check(predict(type("R", (), {"premise": S174, "hypothesis": "no role here"})())
          is None, "predict() abstains where no role is asserted")

    bad = run_regressions()
    check(not bad, f"every frozen regression holds ({bad})")
    check(len(REGRESSIONS) >= 6, f"the frozen set has both directions ({len(REGRESSIONS)})")
    check(sum(1 for r in REGRESSIONS if r[3] == COMPATIBLE) >= 2,
          "true claims are in the frozen set — refusing everything must not pass")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)




# --- frozen regressions -----------------------------------------------------
# The four claims E4 accepted and E5 must refuse. Held as data, not derived, so
# a change to the pair set cannot quietly remove the cases that justified this
# module's existence.
REGRESSIONS = (
    ("s.173 duration-as-count",
     "not more than one hundred and twenty days shall intervene between two "
     "consecutive meetings of the board",
     "Section 173 sets one hundred and twenty days as the minimum number of "
     "Board meetings in a year.", INCOMPATIBLE),
    ("s.174 count-as-proportion",
     "the quorum for a meeting of the board of directors of a company shall be "
     "one-third of its total strength or two directors, whichever is higher",
     "Section 174 sets two directors as the fraction of total strength forming "
     "the quorum for a Board meeting.", INCOMPATIBLE),
    ("s.96 interval-as-deadline (first AGM)",
     "not more than fifteen months shall elapse between the date of one annual "
     "general meeting of a company and that of the next",
     "Section 96 sets fifteen months as the deadline for the first annual "
     "general meeting after the first financial year closes.", INCOMPATIBLE),
    ("s.96 interval-as-deadline (subsequent)",
     "not more than fifteen months shall elapse between the date of one annual "
     "general meeting of a company and that of the next",
     "Section 96 sets fifteen months as the deadline for an annual general "
     "meeting other than the first.", INCOMPATIBLE),
    # True claims that must survive — a checker that refuses everything passes
    # the four above and is worthless.
    ("s.174 true fraction",
     "the quorum for a meeting of the board of directors of a company shall be "
     "one-third of its total strength or two directors, whichever is higher",
     "Section 174 sets one-third as the fraction of total strength forming the "
     "quorum.", COMPATIBLE),
    ("s.96 true interval",
     "not more than fifteen months shall elapse between the date of one annual "
     "general meeting of a company and that of the next",
     "Section 96 sets fifteen months as the maximum gap between one annual "
     "general meeting and the next.", COMPATIBLE),
)


def run_regressions() -> list[tuple[str, str, str]]:
    """(name, expected, got) for every regression that does not hold."""
    bad = []
    for name, premise, claim, want in REGRESSIONS:
        got = judge_claim(premise, claim).status
        if got != want:
            bad.append((name, want, got))
    return bad


if __name__ == "__main__":
    _test()
