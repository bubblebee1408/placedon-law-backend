#!/usr/bin/env python3
"""Per-document-class validity rules, citing HELD provisions only.

A-021. Maps each document class to the Rules that govern its retention or
validity period. Classes with no applicable held provision return an empty
list — that is NOT_DETERMINED, which is honest.

Only the Companies Act 2013 is HELD. Contract-governed classes (nda,
services_agreement, etc.) would need the Indian Contract Act 1872, which
is DECLARED but not HELD — so they get no rule.

Run: PYTHONPATH=. python3 checker/validity_rules.py --test
"""
from __future__ import annotations

from checker.doc_validity import Rule

CA2013 = "CA2013"

# ── Rules ──────────────────────────────────────────────────────────────
# Each quote is verbatim from the corpus JSON. `unlimited=True` means
# the provision establishes the document as evidence with no expiry —
# a positive finding of CURRENT, not an absence of information.

_S118_7 = Rule(
    body=CA2013,
    citation="s.118(7)",
    quote="The minutes kept in accordance with the provisions of this section shall be evidence of the proceedings recorded therein.",
    unlimited=True,
)

_S128_5 = Rule(
    body=CA2013,
    citation="s.128(5)",
    quote="The books of account of every company relating to a period of not less than eight financial years immediately preceding a financial year",
    unlimited=False,
)

VALIDITY_RULES: dict[str, list[Rule]] = {
    "board_minutes": [_S118_7],
    "board_resolution": [_S118_7],
    "shareholder_resolution": [_S118_7],
    # financial_statement is not yet a classifier class; add _S128_5 when it is
    # Contract-governed — Indian Contract Act 1872 is DECLARED, not HELD
    "nda": [],
    "services_agreement": [],
    "employment_agreement": [],
    "lease": [],
    "loan_agreement": [],
    "share_purchase_agreement": [],
    # No specific held provision
    "board_notice": [],
    "policy": [],
    "invoice": [],
    "unknown": [],
}


def rules_for(doc_class: str) -> list[Rule]:
    """Return the validity rules for a document class. Empty = NOT_DETERMINED."""
    return VALIDITY_RULES.get(doc_class, [])


def all_covered_classes() -> set[str]:
    """Classes with at least one rule."""
    return {cls for cls, rules in VALIDITY_RULES.items() if rules}


# ── Self-tests ─────────────────────────────────────────────────────────

def _test():
    import sys
    from checker.doc_classifier import CLASSES
    from checker import scope

    passed = 0

    def check(cond, msg):
        nonlocal passed
        if not cond:
            print(f"  [FAIL] {msg}", file=sys.stderr)
            sys.exit(1)
        print(f"  [PASS] {msg}")
        passed += 1

    # Every CLASSES member has an entry (even if empty)
    for cls in CLASSES:
        check(cls in VALIDITY_RULES, f"class '{cls}' has an entry in VALIDITY_RULES")

    # No extra classes in VALIDITY_RULES beyond CLASSES
    for cls in VALIDITY_RULES:
        check(cls in CLASSES, f"VALIDITY_RULES key '{cls}' is a known class")

    # Every rule cites a held body
    for cls, rules in VALIDITY_RULES.items():
        for r in rules:
            b = scope.body(r.body)
            check(b is not None and b.answerable, f"rule for '{cls}' cites held body {r.body}")

    # board_minutes has at least one rule citing s.118
    bm_rules = rules_for("board_minutes")
    check(any("118" in r.citation for r in bm_rules),
          "board_minutes has a rule citing s.118")

    # board_resolution has the same s.118(7) rule
    br_rules = rules_for("board_resolution")
    check(any("118" in r.citation for r in br_rules),
          "board_resolution has a rule citing s.118")

    # unknown returns empty
    check(rules_for("unknown") == [], "unknown class returns empty list")

    # nda returns empty (Contract Act not held)
    check(rules_for("nda") == [], "nda returns empty (Contract Act not held)")

    # nonexistent class returns empty
    check(rules_for("doesnotexist") == [], "nonexistent class returns empty")

    # all_covered_classes is correct
    covered = all_covered_classes()
    check(covered == {"board_minutes", "board_resolution", "shareholder_resolution"},
          f"covered classes = {sorted(covered)}")

    # s.118(7) rule is unlimited
    check(_S118_7.unlimited, "s.118(7) rule is unlimited (evidence, no expiry)")

    # s.128(5) is defined but not wired (no financial_statement class yet)
    check(not _S128_5.unlimited, "s.128(5) rule is not unlimited (8 financial years)")

    # Quotes are non-empty strings
    for cls, rules in VALIDITY_RULES.items():
        for r in rules:
            check(len(r.quote) > 20, f"rule for '{cls}' has a substantive quote ({len(r.quote)} chars)")

    print(f"\n{passed}/{passed} passed")


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        print("validity_rules")
        _test()
    else:
        for cls in sorted(VALIDITY_RULES):
            rules = rules_for(cls)
            if rules:
                for r in rules:
                    tag = "UNLIMITED" if r.unlimited else "INTERVAL"
                    print(f"  {cls}: {r.citation} ({tag})")
            else:
                print(f"  {cls}: NOT_DETERMINED")
