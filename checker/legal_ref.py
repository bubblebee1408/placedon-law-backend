"""
Instrument-qualified references for Indian legal provisions.

The problem this exists to prevent, found while building the section index: the India Code
full-Act PDF reproduces subordinate Rules alongside the Act, and Rules renumber from 1. So "56"
names two different provisions in the same file --

    Companies Act 2013, s.56          Transfer and transmission of securities
    Meetings-of-Board Rules 2014, r.56  Director to intimate Director Identification Number

-- and a lookup keyed on the number alone silently returns whichever was indexed first. That is a
wrong legal answer with full confidence attached, which is the worst failure this system can have.

A provision number is therefore NEVER an identity here. Identity is (instrument, number). Week 2
ingests the subordinate Rules into the same store, so this has to hold before that happens, not
after.

Run: python3 checker/legal_ref.py
"""
from __future__ import annotations

import re
from dataclasses import dataclass

ACT = "ACT"
RULE = "RULE"
_PREFIX = {ACT: "S", RULE: "R"}
_KEY = re.compile(r"^(ACT|RULE):([A-Z0-9_]+):([SR])([0-9]{1,3}[A-Z]{0,3})$")


class AmbiguousReference(LookupError):
    """Raised when a number alone identifies more than one provision. Never resolved by guessing."""


@dataclass(frozen=True)
class LegalRef:
    instrument_type: str          # ACT | RULE
    instrument_id: str            # COMPANIES_ACT_2013
    number: str                   # 56, 3A, 378ZA
    title: str = ""
    source_id: str | None = None  # India Code sectionID, where one exists

    def key(self) -> str:
        return f"{self.instrument_type}:{self.instrument_id}:{_PREFIX[self.instrument_type]}{self.number}"

    def cite(self) -> str:
        kind = "s." if self.instrument_type == ACT else "r."
        name = self.instrument_id.replace("_", " ").title()
        return f"{name}, {kind}{self.number}" + (f" ({self.title})" if self.title else "")


def parse_key(key: str) -> LegalRef:
    m = _KEY.match(key)
    if not m:
        raise ValueError(f"not a qualified legal reference: {key!r}")
    kind, instrument, prefix, number = m.groups()
    if prefix != _PREFIX[kind]:
        raise ValueError(f"prefix {prefix!r} does not match instrument type {kind!r}: {key!r}")
    return LegalRef(kind, instrument, number)


def resolve(refs: list[LegalRef], number: str, instrument_id: str | None = None) -> LegalRef:
    """Resolve a provision number to exactly one reference.

    Without an instrument this raises on collision rather than picking one. Callers that cannot
    supply an instrument have not established what law they are talking about, and the honest
    answer there is a question, not a provision.
    """
    hits = [r for r in refs if r.number == number
            and (instrument_id is None or r.instrument_id == instrument_id)]
    if not hits:
        raise LookupError(f"no provision numbered {number!r}"
                          + (f" in {instrument_id}" if instrument_id else ""))
    if len(hits) > 1:
        raise AmbiguousReference(
            f"{number!r} names {len(hits)} provisions: "
            + "; ".join(f"{r.key()} ({r.title})" for r in hits)
            + " -- supply instrument_id")
    return hits[0]


# The real collision, kept as a fixture so the regression is permanent.
COLLISION_FIXTURE = [
    LegalRef(ACT, "COMPANIES_ACT_2013", "56", "Transfer and transmission of securities", "1247"),
    LegalRef(RULE, "COMPANIES_MEETINGS_BOARD_POWERS_2014", "56",
             "Director to intimate Director Identification Number"),
]


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"[PASS] {label}")
        else:
            fail += 1; print(f"[FAIL] {label}")

    act = LegalRef(ACT, "COMPANIES_ACT_2013", "185", "Loan to directors, etc.", "49111")
    check(act.key() == "ACT:COMPANIES_ACT_2013:S185", f"act key -> {act.key()}")
    check(parse_key(act.key()).number == "185", "key round-trips")
    check(parse_key("ACT:COMPANIES_ACT_2013:S3A").number == "3A", "alphanumeric section 3A")
    check(LegalRef(RULE, "X_RULES_2014", "56").key() == "RULE:X_RULES_2014:R56", "rule uses R prefix")

    # The safety property: number alone must NOT resolve across instruments.
    try:
        resolve(COLLISION_FIXTURE, "56")
        check(False, "bare number 56 must raise, not pick one")
    except AmbiguousReference as e:
        check("2 provisions" in str(e), "bare number 56 raises AmbiguousReference")

    check(resolve(COLLISION_FIXTURE, "56", "COMPANIES_ACT_2013").title.startswith("Transfer"),
          "qualified by Act -> Transfer and transmission of securities")
    check(resolve(COLLISION_FIXTURE, "56", "COMPANIES_MEETINGS_BOARD_POWERS_2014")
          .title.startswith("Director to intimate"), "qualified by Rules -> DIN intimation")

    for bad in ("56", "ACT:COMPANIES_ACT_2013:R56", "COMPANIES_ACT_2013:S56", ""):
        try:
            parse_key(bad); check(False, f"{bad!r} must be rejected")
        except ValueError:
            check(True, f"rejects malformed key {bad!r}")

    try:
        resolve(COLLISION_FIXTURE, "999")
        check(False, "unknown number must raise")
    except LookupError:
        check(True, "unknown number raises rather than returning None")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
