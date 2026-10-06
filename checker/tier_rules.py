#!/usr/bin/env python3
"""The five tiers and the one that can verify. RING 0 — the rule, not the connectors.

"Only primary law we hold may make a statement of law VERIFIED" is legal epistemics. It is
the same family as entailment, currency and the deciders, all of which are Ring 0. What sits
in Ring 2 is *which host was read, and when*.

A tier NAME is a judgement about what kind of evidence something is. A tier ASSIGNMENT is an
observation about where it came from. This module holds only the first.

## Why it had to move

T2 requires that only HELD can reach VERIFIED. `checker/sources/tiers.py` said so correctly
and **nothing on the path that assigns VERIFIED consulted it**: a proposition is
`"VERIFIED" if s.traced else "UNVERIFIED"`, `traced` is `verdict == TRACED`, and
`lawyer_summary.verify_sentence` -- which decides TRACED -- had no tier information at all.
A sentence quoting a real span of a LICENSED judgment would have been VERIFIED.

`lawyer_summary` is Ring 0 and `checker.sources` is Ring 2, so it could not ask. Rather than
weaken the firewall, the vocabulary moved inward and the connectors stayed where they are.
Ring 0 still cannot reach any connector, any host, or `checker.sources` itself; it gained
five strings and a predicate over them.

`.claude/loops/DECISION_tier_vocabulary_to_ring0.md` has the decision and its reversal
condition. `checker/sources/tiers.py` now re-exports this module, so every Ring 2 caller and
the documented `checker/sources/__init__.py` surface are unchanged.

Run: PYTHONPATH=. python3 checker/tier_rules.py --test
"""
from __future__ import annotations

HELD = "HELD"
OFFICIAL_LIVE = "OFFICIAL_LIVE"
LICENSED = "LICENSED"
COMPANY_FACT = "COMPANY_FACT"
CLIENT = "CLIENT"

TIERS = (HELD, OFFICIAL_LIVE, LICENSED, COMPANY_FACT, CLIENT)

# The whole point of the file. A tuple and not a set so it prints in a stable order in the
# failure message, and a tuple of ONE so that widening it is a visible edit to this line.
VERIFYING_TIERS = (HELD,)

# Tiers whose sources require attribution by their own terms (read in terms.py: Indian
# Kanoon's RAG-and-logo clause, SEBI's "prominently acknowledged"). An Evidence at one of
# these tiers must carry the terms' own words -- see evidence.py.
ATTRIBUTION_REQUIRED = (LICENSED, COMPANY_FACT)

# What the user is shown. Not decoration: a result rendered without its tier is a result
# whose limits the reader cannot see. `{date}` is filled by the caller from the Evidence's
# own fetched_at, so "read on" can never be a date nobody recorded.
LABELS = {
    HELD: "Verified",
    OFFICIAL_LIVE: "Official, read on {date}",
    LICENSED: "Found in case law",
    COMPANY_FACT: "Company record, {source}, {date}",
    CLIENT: "Your document",
}


class UnknownTier(ValueError):
    """Raised on a tier outside TIERS. Never defaulted: a defaulted tier is a claim."""


def can_verify(tier: str) -> bool:
    """May a claim resting only on this tier be called VERIFIED?

    Raises on an unknown tier rather than returning False. Returning False would be the
    safe direction for a typo, and it would also quietly swallow `can_verify("Held")` --
    a caller getting the answer right by accident while its tier string is wrong
    everywhere else it is used.
    """
    if tier not in TIERS:
        raise UnknownTier(f"{tier!r} is not a tier; one of {TIERS}")
    return tier in VERIFYING_TIERS


def label_for(tier: str, *, date: str = "", source: str = "") -> str:
    """The user-facing label, with the date and source the caller actually holds."""
    if tier not in TIERS:
        raise UnknownTier(f"{tier!r} is not a tier; one of {TIERS}")
    text = LABELS[tier]
    if "{date}" in text and not date:
        raise ValueError(f"the {tier} label names a read date and none was given")
    if "{source}" in text and not source:
        raise ValueError(f"the {tier} label names a source and none was given")
    return text.format(date=date, source=source)


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

    print("tier_rules")

    check(VERIFYING_TIERS == (HELD,),
          f"exactly one tier verifies, and it is HELD ({VERIFYING_TIERS})")
    check(can_verify(HELD), "HELD can verify")
    for t in (OFFICIAL_LIVE, LICENSED, COMPANY_FACT, CLIENT):
        check(not can_verify(t), f"{t} cannot verify")
    check(len(TIERS) == 5 and len(set(TIERS)) == 5, f"five distinct tiers ({TIERS})")

    for bad in ("Held", "held", "", "HELD ", "VERIFIED"):
        try:
            can_verify(bad)
            check(False, f"{bad!r} must raise, not return False")
        except UnknownTier:
            check(True, f"{bad!r} raises UnknownTier rather than returning False -- a "
                        f"caller getting the answer right by accident while its tier string "
                        f"is wrong everywhere else is the bug this prevents")

    check("Verified" not in label_for(LICENSED)
          and "Verified" not in label_for(CLIENT),
          "no non-HELD label contains the word 'Verified'")
    check(label_for(HELD) == "Verified", "HELD reads 'Verified'")

    # The check that `checker/sources/tiers.py` re-exports THESE objects lives in that
    # file's own suite, not here: Ring 0 may not import Ring 2, and `checker/rings.py`
    # refuses the import even inside a test. It caught this, and it caught the same thing in
    # move 6. The firewall holding is worth more than keeping both halves of one assertion
    # in one place.

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    raise SystemExit(_test() if "--test" in sys.argv or len(sys.argv) == 1 else 0)
