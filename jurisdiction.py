"""
Jurisdiction resolution — district > state > national.

This module exists because of one research finding: the PoSH annual-return deadline is set by
the **District Officer**, not nationally. Gurugram notified 28 February; most districts use
31 January. "31 January" is a generalisation, not a rule.

`docs/01_CITATION_GRAPH.md` types `jurisdiction` as ISO 3166-2 — 'IN', 'IN-KA' — which stops at
the state. A district-level obligation sits one level below anything that schema can store, so a
naive lookup finds the state record and confidently answers 31 January for a company whose
district says otherwise. That is exactly the failure this company exists to prevent.

The fix is not "add a district column". It is to make the fallback from district to state
**explicit and refusable**: a record marked `district_scoped` must be matched at district level
or the system abstains. Falling back is the bug.

Pure functions, no I/O. Run: python3 jurisdiction.py
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any


class Level(IntEnum):
    """Specificity of a jurisdiction code. Higher wins."""
    NATIONAL = 0     # 'IN'
    STATE = 1        # 'IN-KA'      (ISO 3166-2)
    DISTRICT = 2     # 'IN-KA-BLR'  (our extension; ISO does not define districts)


class Resolution(str, Enum):
    RESOLVED = "RESOLVED"
    ABSTAIN_DISTRICT_UNKNOWN = "ABSTAIN_DISTRICT_UNKNOWN"
    NO_RECORD = "NO_RECORD"


def level_of(code: str) -> Level:
    """'IN' → NATIONAL, 'IN-KA' → STATE, 'IN-KA-BLR' → DISTRICT."""
    parts = code.split("-")
    if len(parts) == 1:
        return Level.NATIONAL
    if len(parts) == 2:
        return Level.STATE
    if len(parts) == 3:
        return Level.DISTRICT
    raise ValueError(f"Unrecognised jurisdiction code: {code!r}")


def scope_for(state: str, districts: list[str] | None = None) -> list[str]:
    """
    The jurisdiction codes that apply to a company, most specific first.

    A district code must sit under the company's own state — a Bengaluru district code on a
    Maharashtra company is a data error, not a match, and is dropped rather than silently used.
    """
    national = state.split("-")[0]
    out = [d for d in (districts or []) if d.startswith(state + "-")]
    out.append(state)
    out.append(national)
    return out


@dataclass(frozen=True)
class Scoped:
    """
    A jurisdiction-scoped record — a deadline, an obligation, a force_status row.

    `district_scoped` marks an obligation the law delegates to the District Officer. For those,
    a state-level record is *background*, never an answer: if no district record matches, we
    abstain. That single flag is what stops the calendar hardcoding 31 January.
    """
    jurisdiction: str
    payload: Any
    district_scoped: bool = False
    evidence: str | None = None


@dataclass(frozen=True)
class Resolved:
    status: Resolution
    record: Scoped | None
    reason: str
    considered: list[str] = field(default_factory=list)

    @property
    def is_answerable(self) -> bool:
        return self.status is Resolution.RESOLVED


def resolve(records: list[Scoped], state: str, districts: list[str] | None = None) -> Resolved:
    """
    Pick the most specific record that applies, or refuse.

    Refuses in two distinguishable ways, because they need different UI:
      NO_RECORD                 — we have nothing for this jurisdiction at all.
      ABSTAIN_DISTRICT_UNKNOWN  — the obligation is district-set and we don't have this
                                  district's notification. We know a state record exists and
                                  are deliberately not serving it.
    """
    scope = scope_for(state, districts)
    by_code = {r.jurisdiction: r for r in records}

    for code in scope:
        hit = by_code.get(code)
        if hit is None:
            continue
        if hit.district_scoped and level_of(code) is not Level.DISTRICT:
            # A district-set obligation matched only at state/national level. Do not serve it.
            known = sorted(
                r.jurisdiction for r in records if level_of(r.jurisdiction) is Level.DISTRICT
            )
            return Resolved(
                Resolution.ABSTAIN_DISTRICT_UNKNOWN,
                None,
                (
                    f"This obligation is set per district. We have no notification for "
                    f"{districts or ['(no district on profile)']} — the {code} record is "
                    f"background, not an answer."
                    + (f" Districts we do hold: {known}." if known else "")
                ),
                scope,
            )
        return Resolved(Resolution.RESOLVED, hit, f"matched at {code}", scope)

    return Resolved(
        Resolution.NO_RECORD, None, f"no record for any of {scope}", scope
    )


# ─────────────────────────────── tests ───────────────────────────────
if __name__ == "__main__":
    # The PoSH annual return, as the research actually found it:
    #   - Gurugram District Officer notified 28 February
    #   - "31 January" is what most districts use, but it is not a national rule
    #   - Karnataka's district notification was NOT found (BACKLOG H-3)
    POSH_RETURN = [
        Scoped("IN", "no single national date — set by the District Officer",
               district_scoped=True,
               evidence="s.21/22 PoSH Act; deadline fixed by District Officer"),
        Scoped("IN-HR", "state background record", district_scoped=True),
        Scoped("IN-HR-GGN", "28 February", district_scoped=True,
               evidence="Gurugram District Officer notification"),
    ]

    # An obligation that genuinely is national — the IC threshold.
    IC_THRESHOLD = [Scoped("IN", "10 or more employees", district_scoped=False)]

    cases: list[tuple[str, Resolved, Resolution, Any]] = [
        (
            "Gurugram company → district record wins over state",
            resolve(POSH_RETURN, "IN-HR", ["IN-HR-GGN"]),
            Resolution.RESOLVED, "28 February",
        ),
        (
            "Bengaluru company → ABSTAINS, does not fall back to 31 January",
            resolve(POSH_RETURN, "IN-KA", ["IN-KA-BLR"]),
            Resolution.ABSTAIN_DISTRICT_UNKNOWN, None,
        ),
        (
            "Haryana company, district unknown → abstains, refuses the state record",
            resolve(POSH_RETURN, "IN-HR", []),
            Resolution.ABSTAIN_DISTRICT_UNKNOWN, None,
        ),
        (
            "IC threshold is national → resolves with no district needed",
            resolve(IC_THRESHOLD, "IN-KA", ["IN-KA-BLR"]),
            Resolution.RESOLVED, "10 or more employees",
        ),
        (
            "Foreign district code on the profile does not resolve to 28 February",
            resolve(POSH_RETURN, "IN-KA", ["IN-HR-GGN"]),
            Resolution.ABSTAIN_DISTRICT_UNKNOWN, None,
        ),
        (
            "No record at all → NO_RECORD, distinct from a district abstention",
            resolve([], "IN-KA", ["IN-KA-BLR"]),
            Resolution.NO_RECORD, None,
        ),
    ]

    # The DoD's central assertion, stated as its own check:
    ggn = resolve(POSH_RETURN, "IN-HR", ["IN-HR-GGN"])
    blr = resolve(POSH_RETURN, "IN-KA", ["IN-KA-BLR"])
    district_differs = (ggn.record.payload if ggn.record else None) != (
        blr.record.payload if blr.record else None
    )

    failures = 0
    for name, got, want_status, want_payload in cases:
        payload = got.record.payload if got.record else None
        ok = got.status is want_status and payload == want_payload
        failures += (not ok)
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
        print(f"       {got.status.value:26} {got.reason}")
        print(f"       considered: {got.considered}")
        print()

    print(f"[{'PASS' if district_differs else 'FAIL'}] "
          "district-scoped deadline resolves differently from a state-wide one")
    failures += (not district_differs)

    # A Karnataka company must never even *consider* a Haryana district code.
    foreign = resolve(POSH_RETURN, "IN-KA", ["IN-HR-GGN"])
    scope_clean = "IN-HR-GGN" not in foreign.considered
    print(f"[{'PASS' if scope_clean else 'FAIL'}] "
          f"foreign district dropped from scope (considered: {foreign.considered})")
    failures += (not scope_clean)

    total = len(cases) + 2
    print(f"\n{total - failures}/{total} passed")
    raise SystemExit(1 if failures else 0)
