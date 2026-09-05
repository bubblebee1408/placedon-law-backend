# Metric policy and release gate

**Adopted:** 30 Aug 2026. Supersedes "beat the majority baseline on accuracy".

## Why accuracy alone cannot gate this

On the strict set (n=71, 66% negative), **"always NOT_ENTAILED" scores 0.66
accuracy with F1 0.00.** It accepts nothing, ever. Any accuracy threshold below
0.66 passes a system that cannot answer a question.

Afane et al. (CSLAW 2026) measured the same shape on 1,647 statutory-survey
questions: an all-affirmative baseline scored **F1 0.73 against Westlaw AI's
0.64 and Lexis+ AI's 0.41**.

## The gate — four conditions, all required

| condition | threshold | current |
|---|---|---|
| false-accept ceiling | ≤ 10 | **8** |
| F1 floor | ≥ 0.40 | **0.48** |
| abstention cap | ≤ 0.25 | **0.00** |
| per-bucket reporting | required | 3 buckets |

False accepts are capped in **absolute count**, not as a rate, because a rate
hides how many wrong answers a reviewer actually sees.

The majority-class baseline is printed with every result. A score without it is
not a result.

## What the gate rejects

Each module fails it alone, and the failures are diagnostic:

| configuration | verdict | why |
|---|---|---|
| always NOT_ENTAILED | FAIL | F1 0.00, below the floor |
| E3 alone | FAIL | 24 false accepts, over the ceiling |
| E4 alone | FAIL | abstention 0.28, over the cap |
| E5 alone | FAIL | abstention 0.80, over the cap |
| **E5 → E4 → E3 cascade** | **PASS** | 8 / 0.48 / 0.00 |

E5 alone scores accuracy 1.00 and F1 1.00 on the 12 items it decides — and still
fails, because it declines 59 of 71. That is the gate working: perfect
performance on a fifth of the work is not a verifier.

## Module roles

| module | role | may run alone? |
|---|---|---|
| E3 lexical | GENERAL | no — 24 false accepts |
| E4 binding | **SPECIALIST** | no — abstains on 20 of 71 |
| E5 role | **SPECIALIST** | no — abstains on 59 of 71 |

E5 is a specialist verifier module in a cascade. It is not a verifier.

## Per-bucket, cascade

| bucket | n | false accepts | F1 |
|---|---|---|---|
| wrong_binding | 45 | 3 | 0.46 |
| paraphrase | 17 | 0 | 0.58 |
| dropped_qualifier | 9 | **5** | **0.00** |

`dropped_qualifier` is the weakest bucket and the next target: F1 0.00 on 9
items with 5 false accepts. It is under the aggregate ceiling only because it
is small.

## What passing does not mean

Not that grounding is solved. Not that the verifier is general. It means the
configuration did not regress on four axes, measured on 71 human-reviewed pairs
drawn from five provisions of one Act.

## E6 — the qualifier gate (added 2026-08-30)

E6 holds the `GATE` role in `MODULE_ROLES`. A gate may only ever refuse. It runs
first in the cascade and can convert an accept into a refusal, never the
reverse; `checker/metric_policy.py` asserts this against every benchmark row.
The restriction is not a safety margin, it is a statement of competence: E6 does
not know whether a claim binds the right quantity to the right obligation. It
knows only whether the claim carries the qualifiers the provision attaches to
the rule. A module that cannot tell you an answer is right must not be able to
say so.

### Effect on the release gate

| configuration | false accepts | F1 | dropped_qualifier FA |
|---|---|---|---|
| E5 -> E4 -> E3, ungated | 13 | 0.49 | 5 |
| E6 gate + cascade | **2** | **0.51** | **0** |

The ungated cascade now fails the false-accept ceiling; a test pins that, so the
gate cannot be removed without the suite going red.

### A fixture defect found on the way

The `dropped_qualifier` measurement was distorted by the benchmark, not only by
the verifier. The fallback premise in `entail_pairs_v2.constructed_pairs` was
`provision(section)[:400]`, and on s.96 that cut landed inside the first proviso.
The premise stopped before "nine months" while a pair labelled ENTAILED asserted
exactly that: **the premise did not contain the evidence for its own label.**
The fallback is now the whole provision (cap 2500; the longest such section is
1858 characters), and a test asserts the s.96 premise contains its own evidence.

Fixing it raised ungated false accepts from 8 to 13. That is the honest number —
the 8 was partly an artifact of a premise too short to contain the text that
would tempt E3.

### Open: the qualifier inventory has gaps

`QUALIFIERS` is maintained by hand and fails silently. `QUALIFIERS[("174","1")]`
is an **empty list**, which reads as "this provision carries no qualifiers", so
the INVALID_FIXTURE routing never fired and three unqualified positives were
emitted as ENTAILED. s.96 has no key at all.

`entail_qualifier.inventory_gaps()` now reads the served text and reports what
the inventory does not know, with the verbatim trigger and the affected pair
ids. It proposes; it does not relabel. Four gaps stand open:

| section | kind | trigger |
|---|---|---|
| 174 | selector | `whichever is higher` |
| 96 | government_power | `Central Government may exempt any company from the provisions of this sub-section` |
| 96 | subjection | `subject to such conditions as it may impose` |
| 96 | proviso | `provided further that if a company holds its first annual general meeting as aforesaid` |

Under the strict convention these make four `wrong_binding` positives invalid
fixtures, not E6 errors: "Section 174 sets one-third as the fraction of total
strength forming the quorum" drops `whichever is higher`, and on a three-director
board one-third is 1 while the real quorum is 2. E6 refuses them and is scored
against for it — `wrong_binding` F1 reads 0.36 rather than 0.50 because of it.

**These are not relabelled here.** Rebuilding an invalid fixture as a qualified
positive is HUMAN_JUDGED, the same ruling that governs the nine records still
open from the earlier pass. Four more join that queue.
