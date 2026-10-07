"""F3 — which body of law, and whose: Central, a State, or both. Triage, not a finding.

A compound question can reach Central law (the Companies Act, FEMA) AND State law (stamp
duty, which is levied and rated by each State). Before any research runs, something has to
decide WHICH bodies a topic engages and, for a State topic, WHICH State — so the supervisor
(F2) can plan one researcher per (body, State) and refuse the ones we do not hold, by name,
rather than letting a single national answer paper over 25+ different State regimes.

## This decides routing, never law

Every row's constitutional basis is **UNVERIFIED**. We do not hold the Constitution's text,
so the List/Entry a row rests on is a CLAIM to be acquired and reviewed, never asserted as
fact. The resolver says "this topic looks Central / State"; the actual legal answer still
comes only from the held corpus (the Companies Act) or from a named refusal (FEMA, stamp
duty). A wrong routing misroutes a question to a refusal; it never states a wrong rule.

## A State topic with no State, or no date, is NEED_FACT — never a guess

Stamp duty in Karnataka is not stamp duty in Maharashtra, and both change over time. A lease
"in Bengaluru" resolves to Karnataka; a lease with no city and no State named resolves to
**NEED_FACT("Which State?")**. Guessing a State would be the single-national-answer mistake
scope.py's STAMP body already warns about.

The table is REVIEWED (hand-checked topic→jurisdiction), and it is small on purpose: it
carries only the topics the product routes today, each flagged for counsel review.
"""
from __future__ import annotations

from dataclasses import dataclass, field

CENTRAL = "CENTRAL"
STATE = "STATE"
BOTH = "BOTH"
JURISDICTIONS = (CENTRAL, STATE, BOTH)

NEED_FACT = "NEED_FACT"


@dataclass(frozen=True)
class Topic:
    """One reviewed routing row. `basis_verified` is False until the Constitution is acquired."""
    key: str
    jurisdiction: str
    bodies: tuple[str, ...]          # scope.py body keys this topic engages
    basis: str                       # the constitutional List/Entry it RESTS ON — a claim
    basis_verified: bool = False     # UNVERIFIED until acquired and reviewed. Always False today.
    triggers: tuple[str, ...] = ()   # words in a question that reach this topic
    needs_state: bool = False        # a State topic cannot be answered without the State + a date


# The reviewed table. Every `basis` is a CLAIM flagged UNVERIFIED (basis_verified=False) — the
# List/Entry is cited so a reviewer knows what to acquire, never asserted as decided law.
TOPICS: tuple[Topic, ...] = (
    Topic("company_act", CENTRAL, ("CA2013",),
          "Union List (List I), Entries 43-44 — incorporation and regulation of companies",
          triggers=("company", "companies", "director", "board", "shares", "share",
                    "allotment", "allot", "annual return", "agm", "resolution",
                    "meeting", "filing", "roc", "incorporat")),
    Topic("foreign_investment", CENTRAL, ("FEMA1999",),
          "Union List (List I), Entry 36 — foreign exchange; the FDI rules under FEMA",
          triggers=("foreign", "fdi", "fema", "overseas", "non-resident", "nri",
                    "singapore", "offshore", "investor abroad", "foreign investor")),
    Topic("stamp_duty", STATE, ("STAMP",),
          "State List (List II), Entry 63 — stamp duty rates other than the instruments in "
          "Union List Entry 91",
          triggers=("stamp", "stamp duty", "lease", "leases", "conveyance", "deed",
                    "instrument", "franking", "registration charge"),
          needs_state=True),
)
_BY_KEY = {t.key: t for t in TOPICS}

# A reviewed city → State map. Small and explicit: a city not listed yields no State, which
# becomes NEED_FACT rather than a guess. States/UTs, never a national default.
CITY_STATE: dict[str, str] = {
    "bengaluru": "Karnataka", "bangalore": "Karnataka",
    "mumbai": "Maharashtra", "pune": "Maharashtra", "nagpur": "Maharashtra",
    "delhi": "Delhi", "new delhi": "Delhi",
    "chennai": "Tamil Nadu", "hyderabad": "Telangana", "kolkata": "West Bengal",
    "ahmedabad": "Gujarat", "gurugram": "Haryana", "gurgaon": "Haryana",
    "noida": "Uttar Pradesh", "jaipur": "Rajasthan", "kochi": "Kerala",
}


@dataclass(frozen=True)
class Resolution:
    """Where a topic routes, and what is still missing. `need_fact` set => cannot route yet."""
    topic: str
    jurisdiction: str
    bodies: tuple[str, ...]
    basis: str
    basis_verified: bool
    state: str | None = None
    as_of: str | None = None
    need_fact: str | None = None
    detail: dict = field(default_factory=dict)

    @property
    def resolved(self) -> bool:
        return self.need_fact is None


def topic(key: str) -> Topic:
    if key not in _BY_KEY:
        raise KeyError(f"no jurisdiction topic {key!r}; known: {sorted(_BY_KEY)}")
    return _BY_KEY[key]


def state_of_city(city: str) -> str | None:
    """The State a city sits in, or None. Lower-cased, trimmed; never guessed."""
    return CITY_STATE.get((city or "").strip().lower())


def topics_in(text: str) -> tuple[str, ...]:
    """Which reviewed topics a question fragment reaches, by keyword. Order of TOPICS.

    A trigger is a substring match on the lower-cased text — enough to ROUTE, never to
    decide. A fragment that reaches no topic returns (), which the caller treats as
    'nothing I can route', not 'nothing applies'.
    """
    low = (text or "").lower()
    return tuple(t.key for t in TOPICS if any(trig in low for trig in t.triggers))


def resolve(topic_key: str, *, state: str | None = None, city: str | None = None,
            as_of: str | None = None) -> Resolution:
    """Route one topic. A State topic with no State (or no date) is NEED_FACT, never a guess.

    `city` is resolved to a State when `state` is not given. For a State topic, BOTH a State
    and an `as_of` date are required — stamp duty differs by State and changes over time, so
    an answer missing either would answer a different question from the one asked.
    """
    t = topic(topic_key)
    st = state or (state_of_city(city) if city else None)

    if t.needs_state:
        missing = []
        if not st:
            missing.append("Which State? (stamp duty is levied and rated per State, so a "
                           "national answer would be wrong by construction)")
        if not as_of:
            missing.append("As of what date? (State stamp rates change over time)")
        if missing:
            return Resolution(t.key, t.jurisdiction, t.bodies, t.basis, t.basis_verified,
                              state=st, as_of=as_of, need_fact=" ".join(missing),
                              detail={"city": city, "needs": ["state"] * (not st)
                                      + ["as_of"] * (not as_of)})

    return Resolution(t.key, t.jurisdiction, t.bodies, t.basis, t.basis_verified,
                      state=st, as_of=as_of, need_fact=None)


def _test() -> None:
    passed = failed = 0

    def check(cond: bool, label: str) -> None:
        nonlocal passed, failed
        if cond:
            passed += 1
            print(f"  [PASS] {label}")
        else:
            failed += 1
            print(f"  [FAIL] {label}")

    print("jurisdiction")

    # ── every basis is UNVERIFIED: this table routes, it does not decide law ──
    check(all(not t.basis_verified for t in TOPICS),
          "every topic's constitutional basis is UNVERIFIED (we do not hold the Constitution)")
    check(all(t.jurisdiction in JURISDICTIONS for t in TOPICS),
          "every topic routes to a known jurisdiction")

    # ── Central topics resolve without a State ──────────────────────────────
    r = resolve("company_act")
    check(r.resolved and r.jurisdiction == CENTRAL and r.bodies == ("CA2013",),
          f"company matters route CENTRAL to the Companies Act ({r.jurisdiction}, {r.bodies})")
    rf = resolve("foreign_investment")
    check(rf.resolved and rf.bodies == ("FEMA1999",),
          f"foreign investment routes CENTRAL to FEMA ({rf.bodies})")

    # ── a State topic needs the State AND a date, else NEED_FACT ─────────────
    bare = resolve("stamp_duty")
    check(not bare.resolved and bare.need_fact and "Which State?" in bare.need_fact,
          f"stamp duty with no State is NEED_FACT, not a guess ({(bare.need_fact or '')[:30]})")
    no_date = resolve("stamp_duty", state="Karnataka")
    check(not no_date.resolved and "date" in (no_date.need_fact or ""),
          "stamp duty with a State but no date is still NEED_FACT (rates change over time)")

    # ── a city resolves to its State; both sides of the done-when ───────────
    blr = resolve("stamp_duty", city="Bengaluru", as_of="2026-10-07")
    mum = resolve("stamp_duty", city="Mumbai", as_of="2026-10-07")
    check(blr.resolved and blr.state == "Karnataka", f"Bengaluru -> Karnataka ({blr.state})")
    check(mum.resolved and mum.state == "Maharashtra", f"Mumbai -> Maharashtra ({mum.state})")
    check(state_of_city("Nowhere City") is None,
          "an unlisted city yields no State, which becomes NEED_FACT rather than a default")

    # ── keyword triggers reach the right topics (routing, not deciding) ──────
    found = topics_in("5-year office leases in Bengaluru and Mumbai, and a share allotment "
                      "to a Singapore investor")
    check("stamp_duty" in found and "company_act" in found and "foreign_investment" in found,
          f"the compound done-when question reaches all three topics ({found})")
    check(topics_in("what is the quorum for a board meeting") == ("company_act",),
          "a plain Companies-Act question reaches only the company topic")
    check(topics_in("the weather today") == (),
          "a fragment that matches nothing routes nowhere, not to a default body")

    print(f"{passed}/{passed + failed} passed")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
