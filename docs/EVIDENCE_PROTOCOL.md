# Evidence Protocol

Replaces the previous "30 practising-CS interviews before proceeding" gate, which is retired with
the scope change to corporate lawyers.

## Evidence tiers, strongest first

| Tier | Method | What it proves | Status |
|---|---|---|---|
| 1 | **Corporate-law task benchmark** | Whether the system works | **Buildable now, no humans needed** |
| 2 | Accessible legal testers | Where time goes, what evidence is demanded | Buildable now |
| 3 | Public workflow research | What tasks recur | Partially done |
| 4 | Competitor analysis | Whether anyone does citations, historical versions, effective dates | Substantially done |
| 5 | **Practising-lawyer expert review** | Professional-use claims | **Required before any accuracy claim** |

Tier 5 is not optional — it gates *claims*, not *development*. Build through tiers 1-4; do not
assert professional validity until a practising corporate lawyer has reviewed the system.

## Tier 1 — the benchmark. This is the critical path.

30-50 controlled documents:
- compliant examples
- **deliberately defective examples** — currently missing entirely; false negatives have never been
  measured because every document in `corpus/testdocs/` is compliant
- multiple document types
- amendment and effective-date cases
- ambiguous cases that **should** trigger "needs human review"

Measured: precision · recall · false positives · **false negatives** · citation correctness ·
effective-date correctness · appropriate abstention rate.

**Non-circularity rule:** expected labels must come from a source independent of the parser input.
The first attempt at this failed exactly here. See `docs/RETRACTIONS.md` R-1.

## Tier 2 — accessible testers

Corporate-law students, junior associates, legal interns, law-firm researchers. Give them the same
tasks as the benchmark and record where time goes and what evidence they demand before trusting a
finding.

**Labelling rule:** never present law-student feedback as lawyer validation. Record the tester's
role and experience on every data point.

## The four questions that replace "would you buy this?"

Hypothetical enthusiasm is weak evidence. Ask about behaviour that already happened:
1. Walk me through the last corporate document you reviewed — what did you check first?
2. How do you currently check what the law was on the relevant date?
3. What would you need to see before trusting an automated finding?
4. What do you still do manually after using your current tools?

## Claim discipline

Every claim carries a classification:
VERIFIED_PRIMARY · VERIFIED_SECONDARY · REASONABLE_INFERENCE · ANECDOTE · UNVERIFIED · RETRACTED

Recorded in `docs/CLAIMS_LEDGER.md`. A claim without a classification does not go into product copy,
a deck, or a conversation with an investor.
