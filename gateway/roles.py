#!/usr/bin/env python3
"""Who may call what. Three roles, one table, and no verb without an entry.

8a. The property that matters is not the three names -- it is that **every verb has a
declared minimum role, checked by the gate**. A permission model where a new verb defaults
to "allowed" is a permission model that silently widens every time someone adds a feature,
and nobody notices until the feature is one that signs off a legal finding.

So `REQUIRED` is exhaustive over `gateway/verbs.VERBS`, `_test` asserts that in both
directions, and a verb added without a line here fails the build.

## The three

    viewer   read what the firm has. Cannot change anything, cannot sign anything off.
    lawyer   everything a viewer can, plus run work and SIGN OFF on findings.
    admin    everything a lawyer can, plus invite and remove people.

They are ordered, and `may()` is a `>=` over that order. A flat set of permissions per role
would let "viewer" drift into being able to do something "lawyer" cannot, which is a state
nobody intends and no reviewer would notice.

## Signing off is the line that matters

`runs.approve` and `runs.reject` are LAWYER, not viewer, and that is the whole reason this
file exists rather than a read_only flag. `gateway/verbs.py` already keeps write verbs off
MCP; what it cannot express is that approving a finding is a professional act and reading
one is not. A viewer who could approve would turn an unreviewed finding into a reviewed one
with no lawyer involved, and `decisions` would record it as labelled data for CAL-1.

Run: PYTHONPATH=. python3 gateway/roles.py --test
"""
from __future__ import annotations

__all__ = ["VIEWER", "LAWYER", "ADMIN", "ROLES", "RANK", "REQUIRED", "may", "rank",
           "RoleError"]

VIEWER = "viewer"
LAWYER = "lawyer"
ADMIN = "admin"

# Ordered, least first. `may()` is a comparison over this.
ROLES = (VIEWER, LAWYER, ADMIN)
RANK = {name: i for i, name in enumerate(ROLES)}


class RoleError(ValueError):
    """An unknown role. Never silently treated as the lowest one."""


def rank(role: str) -> int:
    if role not in RANK:
        raise RoleError(f"{role!r} is not a role; one of {ROLES}")
    return RANK[role]


# Every verb, with the LEAST role that may call it. Exhaustive by test.
#
# The default for anything new is deliberately absent rather than VIEWER: a missing entry
# is a build failure, and a build failure is the only kind of reminder that works.
REQUIRED: dict[str, str] = {
    # ── reading ─────────────────────────────────────────────────────────────
    "ask": VIEWER,
    "citation.get": VIEWER,
    "conversation.get": VIEWER,
    "conversation.list": VIEWER,
    "draft.diff": VIEWER,
    "draft.export": VIEWER,
    "draft.status": VIEWER,
    "draft.versions": VIEWER,
    "events.assess": VIEWER,
    "intake.classify": VIEWER,
    "review_document": VIEWER,
    "review_table.export": VIEWER,
    "review_table.status": VIEWER,
    "runs.get": VIEWER,
    "runs.trace": VIEWER,
    "sources.list": VIEWER,
    "sources.search": VIEWER,

    # ── doing work ──────────────────────────────────────────────────────────
    # A viewer may read a contract review someone else ran; running one spends money and
    # writes a run, so it is a lawyer's act.
    "company_facts.extract": LAWYER,
    "conversation.send": LAWYER,
    "documents.upload": LAWYER,
    "draft.create": LAWYER,
    "draft.revise": LAWYER,
    "review_contract": LAWYER,
    "review_table.cancel": LAWYER,
    "review_table.create": LAWYER,
    "runs.cancel": LAWYER,
    "runs.submit": LAWYER,

    # ── signing off ─────────────────────────────────────────────────────────
    # The line this file exists for. A decision here becomes labelled data (CAL-1) and the
    # record that a person reviewed a finding.
    "runs.approve": LAWYER,
    "runs.reject": LAWYER,
}


def may(role: str, verb: str) -> bool:
    """Is `role` permitted to call `verb`?

    An unknown VERB is refused, not allowed. The alternative -- treating a verb with no
    entry as public -- is exactly the silent widening this file exists to prevent, and it
    would happen at runtime on the one deployment where the test did not run.
    """
    need = REQUIRED.get(verb)
    if need is None:
        return False
    return rank(role) >= rank(need)


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

    print("roles")
    from gateway.verbs import VERBS

    names = {v.name for v in VERBS}
    # ── exhaustive, in BOTH directions ──────────────────────────────────────
    missing = sorted(names - set(REQUIRED))
    check(not missing,
          f"**every verb declares a minimum role** -- a verb added without one fails this "
          f"build, which is the only kind of reminder that works ({missing})")
    extra = sorted(set(REQUIRED) - names)
    check(not extra,
          f"...and no role is declared for a verb that no longer exists, which would be a "
          f"permission nobody can see being granted ({extra})")
    check(all(r in ROLES for r in REQUIRED.values()),
          "every declared role is one of the three")

    # ── the roles are ORDERED, not a flat set ───────────────────────────────
    check(ROLES == (VIEWER, LAWYER, ADMIN) and rank(VIEWER) < rank(LAWYER) < rank(ADMIN),
          "the roles are ordered least-first, so `may` is a comparison and 'viewer' "
          "cannot drift into doing something 'lawyer' cannot")
    for verb in REQUIRED:
        check_all = all(may(ADMIN, verb) for _ in (1,))
        if not check_all:
            check(False, f"admin may call {verb}")
    check(all(may(ADMIN, v) for v in REQUIRED),
          "an admin may call every verb")
    check(all(may(LAWYER, v) for v in REQUIRED if REQUIRED[v] != ADMIN),
          "a lawyer may call everything not reserved to admin")

    # ── the line this file exists for ───────────────────────────────────────
    check(REQUIRED["runs.approve"] == LAWYER and REQUIRED["runs.reject"] == LAWYER,
          "signing off is LAWYER")
    check(not may(VIEWER, "runs.approve") and not may(VIEWER, "runs.reject"),
          "**a viewer may NOT approve or reject a finding** -- it would turn an unreviewed "
          "finding into a reviewed one with no lawyer involved, and `decisions` would "
          "record it as labelled data for CAL-1")
    check(may(VIEWER, "runs.get") and may(VIEWER, "runs.trace"),
          "...while a viewer may READ the run and its trace: reading a finding is not a "
          "professional act and signing one off is")
    check(not may(VIEWER, "review_contract") and may(VIEWER, "review_document"),
          "running a contract review spends money and writes a run (lawyer); reading the "
          "deterministic document check does not")
    check(not may(VIEWER, "documents.upload"),
          "a viewer cannot put a document in")

    # ── an unknown verb is REFUSED, not allowed ─────────────────────────────
    check(not may(ADMIN, "widgets.delete"),
          "an unknown verb is refused even for an ADMIN: treating an unmapped verb as "
          "public is the silent widening this file exists to prevent, and it would happen "
          "on the one deployment where the test did not run")
    try:
        rank("superuser")
        check(False, "an unknown role raises")
    except RoleError:
        check(True, "an unknown role RAISES rather than being treated as the lowest one")
    check(not may(VIEWER, ""), "an empty verb name is refused")

    # ── every WRITE verb needs at least lawyer ──────────────────────────────
    writes = {v.name for v in VERBS if not v.read_only}
    weak = sorted(w for w in writes if REQUIRED.get(w) == VIEWER)
    check(not weak,
          f"NO write verb is open to a viewer -- read_only is about MCP exposure and this "
          f"is about who may act, and the two must not disagree ({weak})")
    reads = {v.name for v in VERBS if v.read_only}
    check(all(REQUIRED[r] in (VIEWER, LAWYER) for r in reads),
          "no read verb is reserved to admin: there is nothing to read that only an "
          "administrator should see")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_test())
    print(__doc__)
