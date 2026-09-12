"""The one gate between "we hold this" and "a user may see it".

## The problem this exists to fix

"Only SERVABLE reaches a user" was, before this module, reimplemented in six
independent places under two vocabularies:

    evidence_pack.usable_for_answering   provenance.SERVABLE + defects + text
    prescribed_thresholds.Threshold      provenance.SERVABLE
    s188_threshold (three call sites)    provenance.SERVABLE, hand-rolled
    assessment.servable_conclusion       CONCLUSIVE_STATUSES = (ADMITTED,)
    admission.ready_for_production       SERVABLE_STATES -- a SEPARATE vocabulary
    event_log.Event.__post_init__        the verified_by invariant

No shared base class, no registry, no adapter. The single bridge between the
evidence axis and the output-class axis was one property on Threshold.

That was survivable while statute was the only corpus, because the Gazette is
public and every gate asked the same question about the same kind of thing. It
stops being survivable the moment a second class of data exists: a licensed price
or a telemetry observation would bypass all six, and nothing in the suite would
notice, because every gate is tested inside its own module and there is no
cross-cutting invariant.

## What this module does NOT do

It does not collapse the six into one predicate. Three of them ask genuinely
different questions -- whether a corpus record is admitted, whether a conclusion
rests on an ADMITTED provision, whether an event has a verifier -- and flattening
those into one call would be a false unification that loses meaning.

What it does is own the **common core** (is this evidence state servable, and does
its licence permit release) and REGISTER the rest, so that the set of gates is
enumerable, tested, and cannot silently grow a seventh member. `_test` scans the
tree for `in SERVABLE` outside this module and fails on any site not on the list.

## Why a reason, never a bare bool

A refusal a user cannot read is indistinguishable from a bug. Every `Release`
carries the sentence explaining it, so the caller has something to render instead
of a blank cell -- which is the same reason `prescribed_thresholds` raises
`ThresholdUnavailable` with a note rather than returning None.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from checker import provenance as prov

ROOT = Path(__file__).resolve().parent.parent

# Licence capabilities (Axis D). Declared here so release.py can reason about
# them; the per-feed registry and its human attestation land in licence.py (T5).
# A frozenset, NOT a ladder: a feed may be showable but not storable, or storable
# but not showable. Conflating those repeats the mistake provenance.py:38-40
# documents about conflating evidence with accessibility.
MAY_SHOW = "MAY_SHOW"

# Every place that independently decides whether something may reach a user.
# (module, symbol, what it adds beyond the evidence state)
@dataclass(frozen=True)
class Gate:
    module: str
    detail: str
    shares_vocabulary: bool     # True => uses provenance.SERVABLE


GATES = (
    Gate("evidence_pack.usable_for_answering",
         "adds blocking defects and the presence of raw text", True),
    Gate("prescribed_thresholds.Threshold.servable",
         "the prescribed amount's own evidence state", True),
    Gate("s188_threshold", "lookup/available/servable, three call sites", True),
    Gate("assessment.servable_conclusion",
         "a DIFFERENT question: is the provision ADMITTED and applicability definite",
         False),
    Gate("admission.ready_for_production",
         "a SEPARATE vocabulary: PRODUCTION_USABLE / DEFECT_FLAGGED_PRODUCTION_LIMITED",
         False),
    Gate("event_log.Event.__post_init__",
         "the verified_by invariant: no verifier => never a VERIFIED_FACT", False),
)

# Files permitted to test `in SERVABLE` directly, with the reason each is allowed.
# Anything else must call may_release(). Enforced by _test.
_ALLOWED_DIRECT = {
    "checker/provenance.py": "defines SERVABLE",
    "checker/release.py": "is the gate",
    "checker/admission.py": "a separate vocabulary (SERVABLE_STATES), not this one",
    "checker/prescribed_thresholds.py": "routed through may_release; property kept for callers",
    "checker/s188_threshold.py": "routed through may_release; property kept for callers",
}


@dataclass(frozen=True)
class Release:
    """May this reach a user, and if not, the sentence that says why."""
    allowed: bool
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.allowed and not self.reason.strip():
            raise ValueError("a refusal must carry a reason a user can read")
        if self.allowed and self.reason:
            raise ValueError("an allowed release states no reason; it is not a warning channel")

    def __bool__(self) -> bool:
        return self.allowed


ALLOWED = Release(True)


def may_release(*, evidence_state: str, licence: frozenset[str] | None = None,
                what: str = "this") -> Release:
    """The common core: a servable evidence state, and a licence that permits it.

    `licence=None` means the item carries no redistribution restriction -- statute
    and Gazette, which are public. It does NOT mean "unknown". An unregistered
    feed resolves to the EMPTY frozenset in licence.py and is refused here, which
    is the fail-closed direction.
    """
    if evidence_state not in prov.STATES:
        return Release(False, f"{what}: unknown evidence state {evidence_state!r}")
    if evidence_state not in prov.SERVABLE:
        return Release(False,
                       f"{what}: evidence state {evidence_state} is not servable "
                       f"(servable states: {', '.join(prov.SERVABLE)})")
    if licence is not None and MAY_SHOW not in licence:
        held = ", ".join(sorted(licence)) if licence else "no rights at all"
        return Release(False,
                       f"{what}: held under a licence that does not permit display "
                       f"({held}). The value may exist and still not be showable.")
    return ALLOWED


def _direct_servable_sites() -> dict[str, list[int]]:
    """Every `in SERVABLE` in checker/, by file and line. Used by the invariant."""
    pat = re.compile(r"\bin\s+(?:prov\.|provenance\.)?SERVABLE\b")
    out: dict[str, list[int]] = {}
    for p in sorted((ROOT / "checker").glob("*.py")):
        rel = f"checker/{p.name}"
        for i, line in enumerate(p.read_text().splitlines(), 1):
            # Stop at the module's own test. A check() asserting that something is
            # NOT servable is the suite doing its job, not a seventh gate, and
            # counting it would make this invariant cry wolf until it was ignored.
            if line.startswith("def _test("):
                break
            if pat.search(line) and "SERVABLE_STATES" not in line:
                out.setdefault(rel, []).append(i)
    return out


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

    print("release")

    # ── the core gate ────────────────────────────────────────────────────────
    check(bool(may_release(evidence_state=prov.VERIFIED)), "a VERIFIED item is released")
    check(bool(may_release(evidence_state=prov.CORROBORATED)), "a CORROBORATED item is released")
    r = may_release(evidence_state=prov.UNRESOLVED, what="s.2(85)")
    check(not r.allowed and "not servable" in r.reason,
          f"an UNRESOLVED item is refused, with a readable reason ({r.reason[:44]}…)")
    check("s.2(85)" in r.reason, "...naming the thing refused, not just the state")
    bad = may_release(evidence_state="NONSENSE")
    check(not bad.allowed and "unknown evidence state" in bad.reason,
          "an unknown state is refused as unknown, not silently treated as unservable")

    # ── the licence axis (Axis D), fail-closed ───────────────────────────────
    check(bool(may_release(evidence_state=prov.VERIFIED, licence=None)),
          "licence=None means public (statute), and releases")
    lic = may_release(evidence_state=prov.VERIFIED, licence=frozenset(), what="a Platts print")
    check(not lic.allowed and "no rights at all" in lic.reason,
          f"an unregistered feed's EMPTY licence is refused ({lic.reason[:50]}…)")
    ok_lic = may_release(evidence_state=prov.VERIFIED, licence=frozenset({MAY_SHOW}))
    check(bool(ok_lic), "a licence carrying MAY_SHOW releases")
    store_only = may_release(evidence_state=prov.VERIFIED,
                             licence=frozenset({"MAY_STORE"}), what="a licensed input")
    check(not store_only.allowed,
          "MAY_STORE without MAY_SHOW is refused — the capabilities are not a ladder")

    # ── a refusal must be readable; an allowance must not smuggle a warning ──
    for args, why in (((False, ""), "a refusal with no reason"),
                      ((True, "careful"), "an allowance carrying a reason")):
        try:
            Release(*args)
            check(False, f"{why} is refused at construction")
        except ValueError:
            check(True, f"{why} is refused at construction")

    # ── THE INVARIANT: the set of gates cannot grow a seventh member unseen ──
    sites = _direct_servable_sites()
    unregistered = {f: ls for f, ls in sites.items() if f not in _ALLOWED_DIRECT}
    check(not unregistered,
          f"no unregistered `in SERVABLE` site exists ({unregistered or 'none'})")
    check(len(GATES) == 6, f"all six known gates are enumerated ({len(GATES)})")
    check(sum(1 for g in GATES if g.shares_vocabulary) == 3,
          "...three share provenance.SERVABLE; three ask a different question")
    check(all(g.detail.strip() for g in GATES),
          "...and each records what it adds, so none is mistaken for a duplicate")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
