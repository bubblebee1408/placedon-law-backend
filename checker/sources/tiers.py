#!/usr/bin/env python3
"""The five tiers, and the one that can make an answer VERIFIED.

PLAN_24 §2. A tier is set by the connector's code and never by a model, so this module
holds no logic a caller can talk round: a predicate, a label table, and two closed tuples.

## Why HELD is alone

`HELD` is `corpus/companies_act/`: 527 hash-stamped sections, cross-rendered against India
Code's own PDF and API, with two confirmed source defects recorded in
`docs/SOURCE_DEFECTS.md` and a corpus status of NOT_FULLY_VERIFIED. That is a low bar in
absolute terms and it is still the only tier that has one at all.

Everything else is evidence about the world rather than law we have checked:

    OFFICIAL_LIVE   read off a government host minutes ago. Nobody ingested it, nothing
                    cross-rendered it, and a consolidation has no history -- so it can say
                    what the page says today and not what the law was on a date
    LICENSED        a judgment on Indian Kanoon. Found and quoted, never verified law
    COMPANY_FACT    a company's own statement about itself, or a registry record. A fact
                    about a company is not a rule about companies
    CLIENT          the document under review. It is the question, not the answer

SEBI asks for this rule in its own website policy: "the same should not be construed as a
statement of law or used for any legal purposes". The publisher agrees with the tier.

Run: PYTHONPATH=. python3 checker/sources/tiers.py --test
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

    print("sources.tiers")
    check(len(TIERS) == 5 and len(set(TIERS)) == 5, f"five distinct tiers: {TIERS}")
    check(VERIFYING_TIERS == (HELD,), "exactly one tier verifies, and it is HELD")
    check(can_verify(HELD), "HELD can verify")
    for t in (OFFICIAL_LIVE, LICENSED, COMPANY_FACT, CLIENT):
        check(not can_verify(t), f"{t} cannot verify")

    for bad in ("Held", "held", "WEB", "", None):
        try:
            can_verify(bad)
            check(False, f"can_verify({bad!r}) raises")
        except (UnknownTier, TypeError):
            check(True, f"can_verify({bad!r}) raises rather than returning False -- a "
                        f"typo must not get the right answer by accident")

    check(set(LABELS) == set(TIERS), "every tier has a user-facing label")
    check(label_for(HELD) == "Verified", "HELD reads 'Verified'")
    check(label_for(OFFICIAL_LIVE, date="2026-09-30") == "Official, read on 2026-09-30",
          "OFFICIAL_LIVE carries the date it was read")
    try:
        label_for(OFFICIAL_LIVE)
        check(False, "...and refuses to render without one")
    except ValueError as e:
        check("read date" in str(e),
              "...and refuses to render without one: 'read on' needs a date")
    try:
        label_for(COMPANY_FACT, date="2026-09-30")
        check(False, "COMPANY_FACT refuses to render without its source")
    except ValueError as e:
        check("source" in str(e), "COMPANY_FACT refuses to render without its source")
    check("Verified" not in label_for(LICENSED)
          and "Verified" not in label_for(CLIENT),
          "no non-HELD label contains the word 'Verified'")
    check(ATTRIBUTION_REQUIRED == (LICENSED, COMPANY_FACT),
          f"attribution is required at {ATTRIBUTION_REQUIRED}")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_test())
    for t in TIERS:
        print(f"  {t:<15} verifies={can_verify(t)!s:<6} {LABELS[t]}")
