# Decision: the tier vocabulary moves to Ring 0. The connectors stay in Ring 2.

**Date** 2026-10-05 · **Move** 7 (T2) · **Branch** `claude/overnight-b`

## The problem

T2 requires that only HELD can make a claim VERIFIED. `checker/sources/tiers.py` already says
so correctly — `VERIFYING_TIERS = (HELD,)`, `can_verify(tier)` — and **nothing on the path
that assigns VERIFIED consults it.**

Measured: a proposition's status is `"VERIFIED" if s.traced else "UNVERIFIED"`, and
`Sentence.traced` is `verdict == TRACED`, decided by `lawyer_summary.verify_sentence`, which
checks that the cited offsets exist and the quote matches byte for byte. It has no tier
information at all: `Source` carries `source_id`, `kind` and `text`. So a sentence quoting a
real span of a LICENSED judgment would be TRACED, and therefore VERIFIED.

Today no LICENSED text can reach `summarise`, because no connector exists. **That is exactly
why this is the right moment:** move 17 builds the Indian Kanoon and data.gov.in skeletons. A
connector landing against an unguarded verifier is how this becomes a defect nobody notices,
and "it cannot happen yet" is not a guard.

## Why this needs a ring change

`checker/rings.py` puts `checker.sources` in **RING 2 (FEEDS)**, with its own comment giving
the reason:

> checker.sources.indiankanoon could rest a legal conclusion on a judgment nobody verified

`lawyer_summary` is reached from Ring 0 and is itself unregistered, so it inherits Ring 0.
A Ring 0 module may not import Ring 2. The firewall caught exactly this in move 6, inside a
test, and it was right to.

## The decision

Split the vocabulary from the connectors.

- **New `checker/tier_rules.py`, RING 0.** The five tier names, `VERIFYING_TIERS`,
  `can_verify`, `ATTRIBUTION_REQUIRED` and the label table. No I/O, no connector, no network.
- **`checker/sources/tiers.py` re-exports it** and keeps its own module API and self-test, so
  every Ring 2 caller is unchanged and `checker/sources/__init__.py`'s documented surface
  still holds.
- `checker.tier_rules` is registered RING_0 in `rings.py`.

**This is where the rule belonged.** "Only primary law we hold can verify a statement of law"
is legal epistemics — the same family as entailment, currency and the deciders, all of which
are Ring 0. What sits in Ring 2 is *which host was read and when*. A tier NAME is a judgement
about what kind of evidence something is; a tier ASSIGNMENT is an observation about where it
came from. The first is core, the second is a feed.

The ring boundary is not weakened: Ring 0 still cannot reach any connector, any host, or
`checker.sources` itself. It gains five string constants and a predicate over them.

## Enforcement

`lawyer_summary.Source` gains a **required** `tier` field — no default.

A default would have been the whole bug again. `HELD` as a default hands the verifying tier to
any future connector author who forgets the argument, which is the person this guard exists to
protect. A least-privileged default would be safer but silent: existing statute sources would
stop verifying and the gate would tell me *somewhere else*. Required means every one of the
eleven construction sites states what kind of evidence it is holding, and anything new cannot
be built without answering the question.

`verify_sentence` then refuses with a new verdict, `TIER_CANNOT_VERIFY`, when a cited source's
tier cannot verify. A refusal, not a downgrade: the sentence may be perfectly true and well
quoted, and what is false is only the claim that *we have verified it*.

## Reversal condition

Reverse if a tier ever needs to carry anything beyond a name — a licence expiry, a host, a
fetch time. Those are observations and belong in Ring 2, and the Ring 0 module would then hold
a name that is a key into Ring 2 data, which is the coupling this split exists to avoid. The
answer in that case is for Ring 2 to pass the already-decided `can_verify` boolean inward,
and for `tier_rules` to shrink to the predicate alone.

Also reverse if `checker/sources/tiers.py` and `checker/tier_rules.py` are ever found to
disagree about `VERIFYING_TIERS`. They cannot, because one re-exports the other, and a check
asserts the identity rather than the equality — but if a future edit makes them two lists,
that is the signal to delete one.
