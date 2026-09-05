# Loop runbook — architecture deep dive, decision-useful not competitive-intel

    pattern : sequential
    mode    : safe
    started : 2026-09-03

## What this is

Not a reconstruction of Spellbook's code — that needs their account (an access
control CLAUDE.md forbids crossing) or invented internals (the fabrication
COMPETITOR_PATTERN_ANALYSIS rejects). Instead: given the design patterns their
public features REQUIRE, which help a lawyer on OUR problem and which hurt, and
what does that imply for our own architecture.

Grounded in our own code and their public statements only. Every competitor
internal stays marked OPEN unless a vendor page states it.

## Stop condition

1. A document mapping each public Spellbook capability to: the design pattern it
   requires, whether that pattern helps or hurts on Indian statutory compliance,
   and the specific file in OUR repo that takes the corresponding position.
2. An honest section on where a lawyer is actually helped vs where the design
   only appears to help.
3. Every claim about their internals marked OPEN; every claim about ours cites a
   file that exists.
4. Committed, pushed, suite green.

## Boundaries

- Public sources only. No account, no authenticated area.
- An OPEN marker is closed only by a vendor statement.
