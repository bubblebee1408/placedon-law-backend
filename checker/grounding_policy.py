"""Strict grounding: what a citation proves, and what it does not.

    A source citation proves that the authority exists.
    It does not prove that the generated proposition follows from the authority.

Those are different facts and the system keeps them apart. A claim is supported
only when its cited evidence entails it **with every material legal
qualification preserved**. A general-rule summary is not supported if its
unqualified wording could mislead a reasonable compliance professional.

## Why unqualified is not "nearly right"

"A private company's meeting is quorate when two members attend" is true of most
private companies and wrong for any whose articles require more — and s.103(1)
opens with exactly that carve-out. A compliance professional acting on the
unqualified sentence holds an inquorate meeting and does not know it. The
citation was genuine; the conclusion was misleading. That gap is the product.

## States

Grounding is a path, not a boolean. Only the last two states may yield GROUNDED:

    CITATION_FOUND            the authority was named
    SOURCE_ADMITTED           it passed the admission gate
    SOURCE_IN_FORCE           it was in force on the relevant date
    CLAIM_PARTIALLY_MATCHED   terms overlap  <- E3 reaches here and no further
    CLAIM_QUALIFIERS_CHECKED  every material qualifier accounted for
    CLAIM_ENTAILED            the proposition follows
    HUMAN_APPROVED            a person signed off

E3's acceptance is `CLAIM_PARTIALLY_MATCHED`. Calling that GROUNDED is the exact
error this module exists to prevent.
"""
from __future__ import annotations

# --- grounding states -------------------------------------------------------
CITATION_FOUND = "CITATION_FOUND"
SOURCE_ADMITTED = "SOURCE_ADMITTED"
SOURCE_IN_FORCE = "SOURCE_IN_FORCE"
CLAIM_PARTIALLY_MATCHED = "CLAIM_PARTIALLY_MATCHED"
CLAIM_QUALIFIERS_CHECKED = "CLAIM_QUALIFIERS_CHECKED"
CLAIM_ENTAILED = "CLAIM_ENTAILED"
HUMAN_APPROVED = "HUMAN_APPROVED"

STATE_ORDER = (
    CITATION_FOUND, SOURCE_ADMITTED, SOURCE_IN_FORCE, CLAIM_PARTIALLY_MATCHED,
    CLAIM_QUALIFIERS_CHECKED, CLAIM_ENTAILED, HUMAN_APPROVED,
)

# Only these may be served as GROUNDED.
GROUNDED_ELIGIBLE = (CLAIM_ENTAILED, HUMAN_APPROVED)

# --- labels -----------------------------------------------------------------
ENTAILED = "ENTAILED"
NOT_ENTAILED = "NOT_ENTAILED"
PENDING_REVIEW = "PENDING_REVIEW"
INVALID_FIXTURE = "INVALID_FIXTURE"

LABELS = (ENTAILED, NOT_ENTAILED, PENDING_REVIEW, INVALID_FIXTURE)

# --- label bases ------------------------------------------------------------
CONSTRUCTED = "CONSTRUCTED"        # follows from a mechanical transformation
HUMAN_JUDGED = "HUMAN_JUDGED"      # requires a person to read the provision
SOURCE_CHECKED = "SOURCE_CHECKED"  # verified verbatim against the source text

BASES = (CONSTRUCTED, HUMAN_JUDGED, SOURCE_CHECKED)

# --- reviewer status --------------------------------------------------------
REVIEW_PENDING = "PENDING_REVIEW"
REVIEW_APPROVED = "APPROVED"
REVIEW_REJECTED = "REJECTED"

# Qualifier categories a positive must preserve to be entailed.
QUALIFIER_KINDS = (
    "proviso",                 # "Provided that ..."
    "exception",               # a carve-out from the general rule
    "threshold",               # a numeric or class threshold that gates the rule
    "scope_limit",             # which companies or meetings the rule reaches
    "delegated_rule",          # "as may be prescribed"
    "articles_override",       # "unless the articles provide otherwise"
    "government_exemption",    # "the Central Government may, by notification..."
)


def state_index(state: str) -> int:
    return STATE_ORDER.index(state)


def may_be_grounded(state: str) -> bool:
    """Only a fully-checked, entailed claim may be served as GROUNDED."""
    return state in GROUNDED_ELIGIBLE


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

    print("grounding_policy")

    check(not may_be_grounded(CLAIM_PARTIALLY_MATCHED),
          "a partially-matched claim is NOT grounded — this is where E3 stops")
    check(not may_be_grounded(CLAIM_QUALIFIERS_CHECKED),
          "checking qualifiers is not by itself entailment")
    check(not may_be_grounded(SOURCE_IN_FORCE),
          "an in-force source does not ground a claim about it")
    check(not may_be_grounded(CITATION_FOUND),
          "finding the authority is not grounding the proposition")
    check(may_be_grounded(CLAIM_ENTAILED) and may_be_grounded(HUMAN_APPROVED),
          "only entailed and human-approved states may be grounded")

    check(state_index(CLAIM_PARTIALLY_MATCHED) < state_index(CLAIM_QUALIFIERS_CHECKED)
          < state_index(CLAIM_ENTAILED) < state_index(HUMAN_APPROVED),
          "the states are strictly ordered")
    check(len(set(STATE_ORDER)) == len(STATE_ORDER), "no state is duplicated")
    check(set(GROUNDED_ELIGIBLE) <= set(STATE_ORDER),
          "every groundable state is a real state")

    check(PENDING_REVIEW in LABELS and INVALID_FIXTURE in LABELS,
          "pending and invalid are first-class labels, not absences")
    check(len(QUALIFIER_KINDS) >= 7, "the qualifier inventory covers the known kinds")
    for k in ("articles_override", "government_exemption", "delegated_rule"):
        check(k in QUALIFIER_KINDS, f"{k} is an enumerated qualifier kind")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
