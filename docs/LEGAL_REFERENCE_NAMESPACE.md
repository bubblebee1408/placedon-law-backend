# Legal reference namespace

**Decision (2026-08-21):** a provision number is never an identity. Identity is
`(instrument_type, instrument_id, number)`. Implemented in `checker/legal_ref.py`.

## Why

While building the section index, the India Code full-Act PDF turned out to reproduce subordinate
Rules alongside the Act. Rules renumber from 1, so "56" names two different provisions in the same
source file:

| Key | Title |
|---|---|
| `ACT:COMPANIES_ACT_2013:S56` | Transfer and transmission of securities |
| `RULE:COMPANIES_MEETINGS_BOARD_POWERS_2014:R56` | Director to intimate Director Identification Number |

A lookup keyed on `56` alone returns whichever was indexed first, with full confidence attached.
That is a wrong legal answer that looks exactly like a right one — the worst failure mode this
system has. It is not hypothetical: it is why s.56 and s.67 mapped to the wrong text before the
title-guided fix.

## Rules

1. Never key a provision by number alone. `resolve(refs, number)` raises `AmbiguousReference` on
   collision instead of choosing.
2. Acts and Rules share no namespace. `ACT:` uses an `S` prefix, `RULE:` uses `R`; a mismatched
   prefix is rejected at parse time.
3. A caller that cannot supply an instrument has not established which law it is talking about.
   The correct response there is a question, not a provision.
4. Unknown numbers raise. Nothing returns a silent `None` that a caller can mistake for absence
   of obligation.

## Bearing on Week 2

Week 2 ingests the subordinate Rules into the same store. This had to land first: retrofitting
identity onto a store that already conflates Acts and Rules means re-verifying everything in it.

## Not yet decided

Versioning within an instrument (an amended rule at two effective dates) is **OPEN**. The current
key has no time component; `checker/as_of.py` handles point-in-time separately. These two need to
be reconciled before rule amendments are ingested.
