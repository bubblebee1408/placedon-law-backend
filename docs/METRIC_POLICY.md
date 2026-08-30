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
