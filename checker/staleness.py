"""Staleness audit — what does the engine's answer rest on, and is anyone watching it?

Written after G.S.R. 880(E). That instrument superseded the small-company limits
on 01-12-2025 and the engine went on serving the 2022 figure as CURRENT for nine
months. The figure was not wrong when it was written. Nothing was watching it.

So this module does not ask "is our law correct" -- it cannot know that. It asks
the answerable question: **for every external instrument our answers depend on,
what is its acquisition state, and would a successor have anywhere to be
recorded?** An instrument nobody watches is the risk, whether or not it has
actually moved.

## The distinction this module refuses to blur

`supersession_watched` does NOT mean "we would find out". Nothing here polls the
Gazette; there is no feed, and acquiring an instrument is a human act by design.
It means only that a successor, once someone records it, has a place to live that
changes the answer -- as 880(E) now does. Discovery is still human. Saying
otherwise would be the same species of false comfort that let 880(E) sit.

## The invariant

An obligation may not report its legal basis CURRENT while a delegated rule it
depends on is unheld or unreviewed. Refusing on the row is not enough: the
currency view is what answers "is this resting on law we have read", and a
CURRENT there is a claim we have read it.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from checker import currency
from checker.lattice import Lattice

# ── acquisition states of an external instrument ──────────────────────────────
HELD_ATTESTED = "HELD_ATTESTED"        # artifact held, both human checks recorded
HELD_UNREVIEWED = "HELD_UNREVIEWED"    # artifact held, nobody has reviewed it
CHAIN_UNRESOLVED = "CHAIN_UNRESOLVED"  # principal held; later amendments are not
CHAIN_TRACED = "CHAIN_TRACED"          # whole chain held and its effects read; awaiting a reader
STAGED = "STAGED"                      # registered for review, refuses until attested
NOT_HELD = "NOT_HELD"                  # we do not have it at all

USABLE = (HELD_ATTESTED,)

# ── exposure: what the acquisition state costs us, given how we use it ────────
OK = "OK"                                  # usable, and a successor has somewhere to land
REFUSED_DISCLOSED = "REFUSED_DISCLOSED"    # not usable, and we say so on the row
CLAIMED_CURRENT_UNHELD = "CLAIMED_CURRENT_UNHELD"   # currency says CURRENT, rule unusable
SERVED_UNWATCHED = "SERVED_UNWATCHED"      # we serve from it and no successor could land

_LATTICE = Lattice("staleness",
                   (OK, REFUSED_DISCLOSED, CLAIMED_CURRENT_UNHELD, SERVED_UNWATCHED))
_SEVERITY = {s: _LATTICE.rank(s) for s in _LATTICE.states}
NEEDS_ACTION = (CLAIMED_CURRENT_UNHELD, SERVED_UNWATCHED)


@dataclass(frozen=True)
class RuleDependency:
    """One external instrument an answer depends on, and how we hold it."""
    rule_id: str
    instrument: str
    governs: tuple[str, ...]              # obligation ids whose answer needs it
    artifact: str | None                  # path, when we hold one
    supersession_watched: bool            # a successor has a place to be recorded
    note: str = ""

    def state(self) -> str:
        """Acquisition state, derived from disk -- never a hand-edited constant."""
        return _acquisition_state(self)


@dataclass(frozen=True)
class Finding:
    rule_id: str
    instrument: str
    acquisition: str
    exposure: str
    governs: tuple[str, ...]
    detail: str

    @property
    def needs_action(self) -> bool:
        return self.exposure in NEEDS_ACTION


def _acquisition_state(dep: RuleDependency) -> str:
    if dep.rule_id == "S-002":
        from scripts.register_gsr700e import registration, is_attested
        rec = registration()
        if rec is None:
            return NOT_HELD
        return HELD_ATTESTED if is_attested(rec) else STAGED
    if dep.rule_id == "S-203-RULES":
        from scripts.register_kmp_rules import registration, is_servable
        rec = registration()
        if rec is None:
            return NOT_HELD
        # Attested or not, the principal Rules alone cannot serve s.203 while five
        # later amendments are unacquired. Any one of them may have moved Rule 8's
        # threshold -- which is exactly how a superseded figure reaches a user.
        if is_servable(rec):
            return HELD_ATTESTED
        return CHAIN_TRACED if rec.get("chain_traced") else CHAIN_UNRESOLVED
    if dep.rule_id == "S-003":
        from scripts.register_gsr880e import registration, is_attested
        rec = registration()
        if rec is None:
            return NOT_HELD
        return HELD_ATTESTED if is_attested(rec) else STAGED
    if dep.artifact is None:
        return NOT_HELD
    if not Path(dep.artifact).is_file():
        return NOT_HELD
    # An artifact on disk that no reviewer has signed off is held, not usable.
    return STAGED if dep.rule_id == "S-188-RULES" else HELD_UNREVIEWED


# ── the inventory. Explicit, like currency.DEPENDENCIES: an instrument appears
# here only where we can name what depends on it. Adding an obligation that rests
# on a new rule without listing it here is caught by the completeness test below.
DEPENDENCIES: tuple[RuleDependency, ...] = (
    RuleDependency(
        "S-002",
        "G.S.R. 700(E), Companies (Specification of Definition Details) Amendment "
        "Rules, 2022, dated 15-09-2022",
        ("CA13-S2-85-SMALL",), "corpus/rules/gsr_700e_2022.txt",
        supersession_watched=True,
        note="held and attested; its window is closed at 30-11-2025 by S-003"),
    RuleDependency(
        "S-003",
        "G.S.R. 880(E), Companies (Specification of Definition Details) Amendment "
        "Rules, 2025, dated 01-12-2025",
        ("CA13-S2-85-SMALL",), None,
        supersession_watched=True,
        note="the operative instrument since 01-12-2025; not held, so the "
             "prescribed limits are refused rather than served"),
    RuleDependency(
        "S-177-RULES",
        "Rule 6, Companies (Meetings of Board and its Powers) Rules, 2014",
        ("CA13-S177-AUDIT-CTTE",), "corpus/rules/board_powers_2014.json",
        supersession_watched=False,
        note="the artifact is held but no reviewer has read it, and no amendment "
             "chain is recorded for it -- a successor would have nowhere to land"),
    RuleDependency(
        "S-188-RULES",
        "Rule 15, Companies (Meetings of Board and its Powers) Rules, 2014 — the "
        "members'-approval thresholds",
        ("CA13-S188-RPT",), "corpus/rules/s188_rule15_review.json",
        supersession_watched=False,
        note="staged for review; the per-type limbs were amended in 2019 and a "
             "reviewer must verify them before they can be served"),
    RuleDependency(
        "S-203-RULES",
        "G.S.R. 249(E), Companies (Appointment and Remuneration of Managerial "
        "Personnel) Rules, 2014 — Rule 8, the prescribed KMP class",
        ("CA13-S203-KMP",), "corpus/rules/kmp_rules_2014.txt",
        supersession_watched=True,
        note="the principal Rules and all five amendments are held, and the chain "
             "is traced: Rule 8 was NEVER amended, so its ten-crore threshold stands "
             "as enacted. Rule 8A was inserted in 2014 and substituted by G.S.R. "
             "13(E) of 2020. s.203 still refuses because a reader must confirm the "
             "resulting text and that rule 8A belongs to the s.203 class"),
)


def rule_usable(rule_id: str) -> tuple[bool, str]:
    """(usable, why-not) for one delegated rule. Read by currency.

    One source of truth for acquisition state: currency asks this rather than
    re-deriving it, so a rule cannot be unusable here and current there.
    """
    for dep in DEPENDENCIES:
        if dep.rule_id != rule_id:
            continue
        acq = dep.state()
        if acq in USABLE:
            return True, ""
        return False, f"{dep.instrument} is {acq}"
    return False, f"{rule_id} is not inventoried in staleness.DEPENDENCIES"


def assess(as_of: date) -> list[Finding]:
    """Every external dependency, worst exposure first."""
    cur = {f.obligation_id: f.status for f in currency.report(as_of)}
    out: list[Finding] = []
    for dep in DEPENDENCIES:
        acq = dep.state()
        usable = acq in USABLE
        claims_current = [o for o in dep.governs if cur.get(o) == currency.CURRENT]

        if usable and dep.supersession_watched:
            exposure, detail = OK, dep.note
        elif usable and not dep.supersession_watched:
            exposure = SERVED_UNWATCHED
            detail = ("we serve answers from this instrument and no successor to it "
                      f"has anywhere to be recorded. {dep.note}")
        elif claims_current:
            exposure = CLAIMED_CURRENT_UNHELD
            detail = (f"{', '.join(claims_current)} reports its legal basis CURRENT, "
                      f"but this rule is {acq}. CURRENT is a claim we have read the "
                      f"law. {dep.note}")
        else:
            exposure = REFUSED_DISCLOSED
            detail = f"not usable ({acq}), and the obligations it governs say so. {dep.note}"

        out.append(Finding(dep.rule_id, dep.instrument, acq, exposure,
                           dep.governs, detail))
    out.sort(key=lambda f: (-_SEVERITY[f.exposure], f.rule_id))
    return out


def exposed(as_of: date) -> list[Finding]:
    """Only the dependencies someone must act on. The audit's alert list."""
    return [f for f in assess(as_of) if f.needs_action]


def unwatched() -> list[RuleDependency]:
    """Instruments whose successor would have nowhere to land. The 880(E) class."""
    return [d for d in DEPENDENCIES if not d.supersession_watched]


def report_text(as_of: date) -> str:
    lines = [f"STALENESS AUDIT — as of {as_of.isoformat()}", ""]
    for f in assess(as_of):
        lines.append(f"  {f.exposure:24} {f.rule_id:14} {f.acquisition}")
        lines.append(f"    governs : {', '.join(f.governs)}")
        lines.append(f"    {f.instrument}")
        lines.append(f"    → {f.detail}")
        lines.append("")
    ex = exposed(as_of)
    lines.append(f"{len(ex)} of {len(DEPENDENCIES)} dependencies need action.")
    lines.append("Nothing here polls the Gazette. Discovery of a successor is human.")
    return "\n".join(lines)


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

    print("staleness")
    today = date(2026, 9, 9)
    findings = assess(today)

    check(len(findings) == len(DEPENDENCIES), "every dependency is assessed")
    check([_SEVERITY[f.exposure] for f in findings]
          == sorted([_SEVERITY[f.exposure] for f in findings], reverse=True),
          "worst exposure sorts first")

    # ── completeness: every delegated rule an obligation names must be listed ──
    import re
    named = set()
    for src in (Path("checker/obligations.py"), Path("checker/currency.py")):
        named |= set(re.findall(r"S-\d{3}-RULES", src.read_text()))
    listed = {d.rule_id for d in DEPENDENCIES}
    check(named <= listed,
          f"every delegated rule named in the code is inventoried (missing: {named - listed})")

    # ── THE INVARIANT ────────────────────────────────────────────────────────
    # An obligation may not report CURRENT while a rule it depends on is unusable.
    # This is the 880(E) defect class, generalised: refusing on the row is not
    # enough, because the currency view is what claims we have read the law.
    bad = [f for f in findings if f.exposure == CLAIMED_CURRENT_UNHELD]
    check(not bad,
          "no obligation reports CURRENT while resting on a rule we have not read "
          f"({[(f.rule_id, f.governs) for f in bad]})")

    # ── and nothing we actually serve from is unwatched ───────────────────────
    served = [f for f in findings if f.exposure == SERVED_UNWATCHED]
    check(not served,
          f"nothing we serve from is unwatched ({[f.rule_id for f in served]})")

    # ── the states are derived from disk, not asserted ────────────────────────
    # The point of this block is that stubbing does not LEAK -- whatever the real
    # state is, it must come back. It used to assert the real state equals
    # NOT_HELD, which quietly became false the day a human attested G.S.R. 880(E),
    # and the suite could not see it because this module had no SystemExit. So the
    # real state is now captured from disk and compared to itself.
    import scripts.register_gsr880e as r880
    before = [f for f in assess(today) if f.rule_id == "S-003"][0].acquisition
    with r880.stub_registration(r880.attested_stub()):
        f880 = [f for f in assess(today) if f.rule_id == "S-003"][0]
        check(f880.acquisition == HELD_ATTESTED,
              f"attesting 880(E) changes its assessed state ({f880.acquisition})")
        check(f880.exposure == OK, f"...and clears its exposure ({f880.exposure})")
    with r880.stub_registration(None):
        f_none = [f for f in assess(today) if f.rule_id == "S-003"][0]
        check(f_none.acquisition == NOT_HELD,
              f"...and with no registration at all it is NOT_HELD ({f_none.acquisition})")
    f880_now = [f for f in assess(today) if f.rule_id == "S-003"][0].acquisition
    check(f880_now == before,
          f"...and the real state is restored afterwards ({f880_now}, was {before})")

    # ── the honest limitation is stated, not implied ──────────────────────────
    check("Discovery of a successor is human." in report_text(today),
          "the report states that nothing polls the Gazette")
    check(bool(unwatched()), "the unwatched list is populated, not empty by construction")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
