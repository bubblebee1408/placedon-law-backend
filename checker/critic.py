#!/usr/bin/env python3
"""The critic: one pass, flag or remove, never add and never rewrite.

PLAN_23 layer 7, under §1.4 (Huang et al., ICLR 2024 — no intrinsic self-correction):

    "Retry only on a reason supplied by an external verifier, at most once, and the retry
     may only NARROW — tighten the question, cut the evidence packet, drop a claim. A
     retry that widens is a second guess dressed as a correction."

So this layer exists to make an answer SMALLER or better-labelled, never bigger. The
research says a model asked to revise without external feedback does not reliably improve
and frequently degrades; a critic allowed to rewrite is exactly that experiment, run on a
legal answer.

## Rewriting is not forbidden, it is unrepresentable

`Note` has `claim_id`, `action` and `reason`. **There is no field for replacement text.**
A critic cannot propose new wording because there is nowhere to put it, which is a
stronger guarantee than a rule saying it must not: a rule can be forgotten by the next
person to add a field, and this cannot be obeyed halfway.

Likewise it cannot ADD: a note naming a claim_id that was not in the input is REFUSED, so
there is no way to attach a critique to something that does not exist and have it appear.

## One narrowing correction per run

Unlimited FLAGs — a flag changes no content, it labels it — and **at most one REMOVE**.
A second removal is not obeyed and not discarded either: it is DOWNGRADED TO A FLAG and
recorded as such. Discarding it would lose a real objection; obeying it would let one pass
gut an answer, which §1.4 rules out. The lawyer sees "the critic also wanted this removed
and was not permitted to" — which is the useful form of the information.

## Every removal is in the trace

`Verdict.trace` records every note the critic made and what was done with it, including
the ones refused. A removal nobody can see is indistinguishable from a claim that was
never made, and the whole point of removing something is that a person may disagree.

Run: PYTHONPATH=. python3 checker/critic.py --test
"""
from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["FLAG", "REMOVE", "ACTIONS", "MAX_REMOVALS", "Note", "Verdict", "review",
           "CriticError"]

FLAG = "FLAG"
REMOVE = "REMOVE"
ACTIONS = (FLAG, REMOVE)

# §1.4: "at most once". One per RUN, not one per claim.
MAX_REMOVALS = 1


class CriticError(ValueError):
    """A critique that cannot be formed. Never a silently ignored note."""


@dataclass(frozen=True)
class Note:
    """One objection. Deliberately has NO replacement-text field -- see the docstring."""
    claim_id: str
    action: str
    reason: str


@dataclass(frozen=True)
class Verdict:
    kept: tuple = ()
    removed: tuple = ()          # (claim_id, reason)
    flagged: tuple = ()          # (claim_id, reason)
    refused: tuple = ()          # (claim_id, action, why the note was not acted on)
    trace: tuple = ()            # every note, in order, with what was done
    note: str = ""

    def to_dict(self) -> dict:
        return {"kept": [dict(c) for c in self.kept],
                "removed": [{"claim_id": i, "reason": r} for i, r in self.removed],
                "flagged": [{"claim_id": i, "reason": r} for i, r in self.flagged],
                "refused": [{"claim_id": i, "action": a, "why": w}
                            for i, a, w in self.refused],
                "trace": list(self.trace), "note": self.note,
                "removals_allowed": MAX_REMOVALS}


# The minimum a reason must say. "wrong" teaches a later reviewer nothing, and a removal
# whose reason is one word is a removal nobody can argue with.
MIN_REASON_CHARS = 10


def review(claims, *, critique) -> Verdict:
    """One pass. `critique(claims) -> [Note | dict]`, injected and called ONCE.

    Called once, by construction: there is no loop here and no re-entry. "At most once" is
    not a counter that could be reset -- it is the shape of the function.
    """
    claims = tuple(dict(c) for c in (claims or ()))
    by_id = {str(c.get("id") or ""): c for c in claims if str(c.get("id") or "")}
    if len(by_id) != len(claims):
        raise CriticError(
            "every claim needs a unique id before it can be criticised; without one a "
            "removal cannot be attributed and the trace would not say what went")

    try:
        raw = list(critique(claims) or [])
    except Exception as e:                                       # noqa: BLE001
        # A critic that breaks changes NOTHING. The answer stands as the verifier left it,
        # which is the safe direction: this layer only ever subtracts.
        return Verdict(kept=claims, trace=(f"the critic did not run ({type(e).__name__}: "
                                           f"{str(e)[:120]}); nothing was changed",),
                       note="The critic did not run. The answer is exactly what the "
                            "verifier produced.")

    removed, flagged, refused, trace = [], [], [], []
    for item in raw:
        n = item if isinstance(item, Note) else Note(
            claim_id=str((item or {}).get("claim_id") or ""),
            action=str((item or {}).get("action") or "").upper(),
            reason=str((item or {}).get("reason") or ""))
        if n.action not in ACTIONS:
            refused.append((n.claim_id, n.action, f"{n.action!r} is not an action this "
                                                  f"layer may take; one of {ACTIONS}"))
            trace.append(f"REFUSED {n.action!r} on {n.claim_id!r}: a critic may only "
                         f"flag or remove")
            continue
        if n.claim_id not in by_id:
            # The ADD guard. A note about a claim that is not there cannot be acted on,
            # and acting on it would be inventing a claim in order to criticise it.
            refused.append((n.claim_id, n.action,
                            "no claim with this id was in the answer, so there is nothing "
                            "to act on. A critic may not introduce one"))
            trace.append(f"REFUSED {n.action} on unknown claim {n.claim_id!r}")
            continue
        if len(n.reason.strip()) < MIN_REASON_CHARS:
            refused.append((n.claim_id, n.action,
                            f"a reason of at least {MIN_REASON_CHARS} characters is "
                            f"required; a removal nobody can argue with is not a review"))
            trace.append(f"REFUSED {n.action} on {n.claim_id!r}: no usable reason")
            continue
        if n.action == REMOVE:
            if len(removed) >= MAX_REMOVALS:
                # Downgraded, not dropped. Both alternatives lose something real.
                flagged.append((n.claim_id, n.reason))
                refused.append((n.claim_id, REMOVE,
                                f"only {MAX_REMOVALS} narrowing correction is permitted "
                                f"per run (PLAN_23 §1.4); this objection is recorded as a "
                                f"FLAG instead of being discarded"))
                trace.append(f"DOWNGRADED REMOVE -> FLAG on {n.claim_id!r}: the one "
                             f"removal was already spent")
                continue
            removed.append((n.claim_id, n.reason))
            trace.append(f"REMOVED {n.claim_id!r}: {n.reason}")
        else:
            flagged.append((n.claim_id, n.reason))
            trace.append(f"FLAGGED {n.claim_id!r}: {n.reason}")

    gone = {i for i, _ in removed}
    kept = tuple(c for c in claims if str(c.get("id") or "") not in gone)
    if removed:
        note = (f"The critic removed 1 claim and flagged {len(flagged)}. The removal is "
                f"in the trace with its reason, because a claim taken out silently cannot "
                f"be told from one that was never made.")
    elif flagged:
        note = (f"The critic removed nothing and flagged {len(flagged)}. A flag changes "
                f"no content; it labels it.")
    else:
        note = "The critic changed nothing."
    return Verdict(kept=kept, removed=tuple(removed), flagged=tuple(flagged),
                   refused=tuple(refused), trace=tuple(trace), note=note)


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

    print("critic")
    import dataclasses as _dc
    CLAIMS = [{"id": "s1", "text": "The quorum is one third or two directors."},
              {"id": "s2", "text": "Notice of seven days is required."},
              {"id": "s3", "text": "Minutes must be entered within thirty days."}]
    R = "the cited provision does not support this as stated"

    # ── rewriting is UNREPRESENTABLE, not merely forbidden ─────────────────
    fields = {f.name for f in _dc.fields(Note)}
    check(fields == {"claim_id", "action", "reason"},
          f"a Note has exactly claim_id, action and reason ({sorted(fields)})")
    check(not any(w in f for f in fields for w in ("text", "replace", "new", "rewrite")),
          "...and NO field for replacement text: a critic cannot propose new wording "
          "because there is nowhere to put it, which a rule could not guarantee")
    check(ACTIONS == (FLAG, REMOVE),
          f"the only actions are FLAG and REMOVE ({ACTIONS})")

    # ── flag: labels, changes nothing ──────────────────────────────────────
    v = review(CLAIMS, critique=lambda c: [{"claim_id": "s2", "action": "FLAG",
                                            "reason": R}])
    check([c["id"] for c in v.kept] == ["s1", "s2", "s3"],
          "a FLAG removes nothing: every claim is still there")
    check(v.flagged == (("s2", R),), "...and the flag is recorded with its reason")
    check(any("FLAGGED 's2'" in t for t in v.trace), "...and is in the trace")

    # ── remove: one, and it is in the trace ────────────────────────────────
    v2 = review(CLAIMS, critique=lambda c: [{"claim_id": "s2", "action": "REMOVE",
                                             "reason": R}])
    check([c["id"] for c in v2.kept] == ["s1", "s3"], "a REMOVE drops that claim")
    check(v2.removed == (("s2", R),), "...and records which, with the reason")
    check(any("REMOVED 's2'" in t and R in t for t in v2.trace),
          "...and EVERY removal is in the trace: a claim taken out silently cannot be "
          "told from one that was never made")
    check("cannot be told from one that was never made" in v2.note,
          "...which the note says in words")

    # ── at most ONE narrowing correction per run ───────────────────────────
    v3 = review(CLAIMS, critique=lambda c: [
        {"claim_id": "s1", "action": "REMOVE", "reason": R},
        {"claim_id": "s2", "action": "REMOVE", "reason": R},
        {"claim_id": "s3", "action": "REMOVE", "reason": R}])
    check(len(v3.removed) == MAX_REMOVALS == 1,
          f"**three removals become ONE** (PLAN_23 §1.4) ({len(v3.removed)})")
    check([c["id"] for c in v3.kept] == ["s2", "s3"],
          "...the first is obeyed and the rest are not")
    check(len(v3.flagged) == 2,
          f"...and the other two are DOWNGRADED TO FLAGS, not discarded ({len(v3.flagged)})")
    check(all(a == REMOVE for _, a, _ in v3.refused) and len(v3.refused) == 2,
          "...with the refusal recorded, so a lawyer sees the critic wanted more removed "
          "and was not permitted to")
    check(any("DOWNGRADED" in t for t in v3.trace), "...and the trace says so")
    check(not any(c["id"] == "s1" for c in v3.kept),
          "...while the one removal that WAS permitted really took effect")

    # ── a critic may not ADD ───────────────────────────────────────────────
    v4 = review(CLAIMS, critique=lambda c: [{"claim_id": "s9", "action": "REMOVE",
                                             "reason": R}])
    check(len(v4.kept) == 3 and not v4.removed,
          "a note about a claim that is NOT in the answer changes nothing")
    check(v4.refused and "may not introduce one" in v4.refused[0][2],
          "...and is refused as an attempt to introduce a claim in order to criticise it")

    # ── a critic may not do anything else ──────────────────────────────────
    for bad in ("REWRITE", "ADD", "EDIT", "AMEND", ""):
        vb = review(CLAIMS, critique=lambda c, b=bad: [{"claim_id": "s1", "action": b,
                                                        "reason": R}])
        check(len(vb.kept) == 3 and vb.refused and "may only" in vb.trace[0],
              f"action {bad!r} is REFUSED and changes nothing")

    # ── a reason is required, and must say something ───────────────────────
    v5 = review(CLAIMS, critique=lambda c: [{"claim_id": "s1", "action": "REMOVE",
                                             "reason": "wrong"}])
    check(len(v5.kept) == 3 and not v5.removed,
          "a removal whose reason is one word is REFUSED: a removal nobody can argue with "
          "is not a review")
    check(v5.refused and "at least 10 characters" in v5.refused[0][2],
          "...and the refusal says what was missing")

    # ── one pass, and a broken critic changes nothing ──────────────────────
    calls = []

    def counting(c):
        calls.append(1)
        return [{"claim_id": "s1", "action": "FLAG", "reason": R}]

    review(CLAIMS, critique=counting)
    check(calls == [1],
          "the critic is called exactly ONCE: 'at most once' is the shape of the "
          "function, not a counter that could be reset")

    def boom(c):
        raise TimeoutError("the critic did not answer")

    v6 = review(CLAIMS, critique=boom)
    check([c["id"] for c in v6.kept] == ["s1", "s2", "s3"] and not v6.removed,
          "a critic that RAISES changes nothing -- the answer stands as the verifier left "
          "it, which is the safe direction for a layer that only subtracts")
    check("did not run" in v6.note, "...and says it did not run")

    v7 = review([], critique=lambda c: [])
    check(v7.kept == () and v7.note == "The critic changed nothing.",
          "no claims and no notes is a clean no-op")
    try:
        review([{"id": "x"}, {"id": "x"}], critique=lambda c: [])
        check(False, "duplicate claim ids raise")
    except CriticError:
        check(True, "DUPLICATE claim ids raise: a removal could not be attributed, and "
                    "the trace would not say what went")

    d = review(CLAIMS, critique=lambda c: [{"claim_id": "s1", "action": "REMOVE",
                                            "reason": R}]).to_dict()
    check(d["removals_allowed"] == 1 and d["removed"][0]["claim_id"] == "s1",
          "to_dict names the bound it applied and what it removed")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_test())
    print(__doc__)
