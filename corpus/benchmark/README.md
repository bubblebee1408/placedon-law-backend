# Entailment benchmark v1.0.0

**human-reviewed, corpus-derived benchmark for selected Indian corporate-law
proposition types**

## What this is not

This benchmark **does not measure general legal grounding**. Its claims are
derived from a handful of provisions of one Act (Companies Act 2013, ss.96, 101,
103, 173, 174), its negatives are constructed, and its positives were written and
approved by one reviewer. It is useful for detecting failure modes and for
comparing checkers against each other. It is **not** evidence that any system is
accurate on real user-generated legal claims.

## Grounding convention — fail-closed

> A claim is supported only when its cited evidence entails it with all material
> legal qualifications preserved. General-rule summaries are not supported if
> their unqualified wording could mislead a reasonable compliance professional.

> A source citation proves that the authority exists. It does not prove that the
> generated proposition follows from the authority.

## Files

| File | Contents |
|---|---|
| `approved_pairs.jsonl` | The frozen set. ENTAILED / NOT_ENTAILED only |
| `rejected_pairs.jsonl` | Rejected pairs with written reasons |
| `invalid_fixtures.jsonl` | Malformed examples, preserved permanently |
| `pending_reviews.jsonl` | Proposals awaiting human review |
| `manifest.json` | Hashes, counts, reviewer IDs, timestamps, commit |
| `entailment_reviews.json` | The human decision record |

## Why invalid fixtures are kept

An invalid fixture is evidence. It records a claim shape that looked correct to
its author and was not — the material a benchmark exists to capture. Nine
fixtures were invalidated because they stated a real quantity-to-obligation
binding unconditionally where the provision carried a qualifier. Each is
preserved with its reason and a pointer to its replacement.

## Reviewer privacy

Reviewers are recorded by pseudonymous ID. The identity map is local and
gitignored: a reviewer's address is not evidence that a claim was reviewed.

## Measured — E3 deterministic baseline

Recorded as `CLAIM_PARTIALLY_MATCHED`. **Never GROUNDED.**

| | |
|---|---|
| n | 71 |
| precision | 0.25 |
| recall | 0.33 |
| **false accepts** | **24/47 (51%)** |
| false rejects | 16/24 (67%) |

The same checker scores 1.00 on a templated set built by altering one checkable
token per claim. The gap between those two numbers is the whole point: token
overlap is not legal entailment. A claim can carry the correct section number,
quantity, date and vocabulary while binding them to the wrong obligation.

**Target for a shippable checker: zero false accepts.** In this domain a false
accept means a legally unsupported statement served as supported; a false reject
means an abstention. Those costs are not symmetric, and frequent abstention is
acceptable for a first release.

## Verifying

    python3 -c "from checker.benchmark_v2_freeze import verify; print(verify() or 'OK')"
