#!/usr/bin/env python3
"""The five tiers, and the one that can make an answer VERIFIED.

PLAN_26 §2. A tier is set by the connector's code and never by a model, so this module
holds no logic a caller can talk round: a predicate, a label table, and two closed tuples.

## Why HELD is alone

`HELD` is `corpus/companies_act/`: 527 hash-stamped sections, cross-rendered against India
Code's own PDF and API, with two confirmed source defects recorded in
`docs/evidence/SOURCE_DEFECTS.md` and a corpus status of NOT_FULLY_VERIFIED. That is a low bar in
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

# RING 0 holds the vocabulary now; this module is the Ring 2 face of it.
#
# The five names, VERIFYING_TIERS, can_verify, label_for and the label table live in
# `checker/tier_rules.py`, because `lawyer_summary` (Ring 0) has to consult them to enforce
# T2 and a Ring 0 module may not import Ring 2. RE-EXPORTED, not re-declared: two lists that
# happen to be equal today are two lists, and `checker/tier_rules.py` asserts the identity of
# these objects rather than their equality.
#
# What stays Ring 2 is everything about WHERE evidence came from -- the connectors, the terms
# records, the fetch times. See .claude/loops/DECISION_tier_vocabulary_to_ring0.md.
from checker.tier_rules import (  # noqa: F401  (re-export)
    ATTRIBUTION_REQUIRED,
    CLIENT,
    COMPANY_FACT,
    HELD,
    LABELS,
    LICENSED,
    OFFICIAL_LIVE,
    TIERS,
    UnknownTier,
    VERIFYING_TIERS,
    can_verify,
    label_for,
)

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

    # ── the re-export is an IDENTITY, not a copy (move 7) ───────────────────
    # The vocabulary lives in `checker/tier_rules.py` (RING 0) so `lawyer_summary` can
    # enforce T2 without importing Ring 2. Two lists that happen to be equal today are two
    # lists, so this asserts the OBJECT: a future edit that forks them fails here rather
    # than drifting until the day they disagree.
    #
    # This check is on the Ring 2 side because Ring 0 may not import Ring 2 -- the firewall
    # refused the mirror image of it, correctly.
    import importlib
    ring0 = importlib.import_module("checker.tier_rules")
    check(VERIFYING_TIERS is ring0.VERIFYING_TIERS,
          f"this module re-exports the SAME tuple object as checker/tier_rules, so the two "
          f"cannot disagree about which tier verifies ({VERIFYING_TIERS})")
    check(can_verify is ring0.can_verify and TIERS is ring0.TIERS
          and LABELS is ring0.LABELS and UnknownTier is ring0.UnknownTier,
          "...and the same predicate, tier list, label table and exception type")
    # By AST, not by text. The first version searched this file for the string
    # `HELD = "HELD"` -- which the check itself contained, so it could never pass. A check
    # that cannot turn green is as useless as one that cannot turn red.
    import ast as _t2_ast
    import inspect as _t2_inspect
    _tree = _t2_ast.parse(_t2_inspect.getsource(
        importlib.import_module("checker.sources.tiers")))
    _assigned = {t.id for node in _tree.body if isinstance(node, _t2_ast.Assign)
                 for t in node.targets if isinstance(t, _t2_ast.Name)}
    check(not (_assigned & set(TIERS) | _assigned & {"TIERS", "VERIFYING_TIERS", "LABELS",
                                                     "ATTRIBUTION_REQUIRED"}),
          f"...and this file DECLARES none of them at module level -- a re-export that also "
          f"assigns is a shadow, and the shadow is what wins ({sorted(_assigned)})")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_test())
    for t in TIERS:
        print(f"  {t:<15} verifies={can_verify(t)!s:<6} {LABELS[t]}")
