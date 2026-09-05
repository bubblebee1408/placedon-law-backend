# Within-section chunk retrieval: does the cross-section fusion win transfer?

Module: `checker/chunk_fusion.py` · Eval: `checker/retrieval_eval.py` · Ranker under test:
`checker/chunk_retrieval.py` (BM25) · Run: k=60, once, no tuning.

Reproduce:

```
PYTHONPATH=. python3 checker/chunk_fusion.py            # 29/29 self-tests
PYTHONPATH=. python3 checker/chunk_fusion.py --measure  # the numbers below
```

## Headline

| Approach | p@1 | recall@5 |
|---|---|---|
| BM25 over structural chunks (shipped) | **8/13 = 0.62** | 12/13 = 0.92 |
| Dense (MiniLM-L6-v2 over chunk text) | **12/13 = 0.92** | 13/13 = 1.00 |
| RRF fusion, k=60 | **10/13 = 0.77** | 13/13 = 1.00 |

BM25 reproduces the recorded 0.62 exactly, which validates that the harness is
measuring the shipped ranker and not a re-implementation.

**Fusion does NOT reproduce the cross-section result. Dense alone beats fusion by
0.15.** On surface 1 fusion was the best of the three (0.80 vs 0.71 / 0.73). Here it
is the middle of the three.

## SMALL SAMPLE — read every number above as provisional

**13 scoreable cases.** One case moves p@1 by 0.08. The whole 0.62 → 0.92 gap is four
cases. This is below the ~15-case floor at which a p@1 is worth quoting without a
caveat attached, and the caveat travels with the number wherever it goes. Nothing here
justifies a claim of the form "dense is 30 points better at within-section retrieval";
it justifies "on 13 cases, dense got 4 more right, and here is exactly which 4 and
why".

**3 NEEDS_LAWYER cases were excluded** (16 cases total, 13 scored). They carry
`expected_path=None` because their correct span is a matter of legal judgement this
project does not have. They were excluded by reusing `retrieval_eval.run`'s own
predicate, not a re-derived one, and no approach was scored on them. Scoring a guessed
label would have made all three numbers above false.

### A second caveat the sample size does not cover

The 13 cases are not a uniform sample of the within-section problem:

- **12 of 13 are in s.2** (170 chunks); **1 is in s.96** (6 chunks). recall@5 over a
  6-chunk pool is nearly free, so the recall@5 column is carried almost entirely by
  s.2 and should not be read as a general recall claim.
- **10 of 13 are the same template**, "the definition of X", where the target chunk
  literally reads `"X" means …`. Query and answer are near-lexical restatements. Dense
  gets 10/10 of these. So dense's 0.92 is substantially a score on near-duplicate
  matching, which is the easiest thing a sentence embedding does.

The three non-definition cases (two s.2(85) limbs, one s.96 proviso) are the ones that
actually probe structural retrieval, and dense goes 2/3 on them. That is the honest
size of the evidence for dense on the hard part of this surface: **three cases**.

## Error-set analysis — the finding that matters

The cross-section run adopted fusion on a specific measured precondition: BM25 and
dense had **nearly disjoint** error sets (11 cases only dense got, 8 only BM25 got).
That is what rank fusion consumes.

On this surface the precondition **fails outright**:

| | count |
|---|---|
| both BM25 and dense correct | 8 |
| **only BM25 correct** | **0** |
| only dense correct | 4 |
| neither correct | 1 |

**BM25's correct set is a strict subset of dense's.** There is not one case in the
scoreable set that BM25 gets and dense misses. Fusion has no complementary signal to
recover, because BM25 contributes nothing dense does not already have. RRF here is not
combining two partial views; it is diluting one good ranker with a strictly worse one.

Per-case predictions:

| expected | BM25 | dense | fusion | question |
|---|---|---|---|---|
| 2(85)(i) | 2(68) ✗ | 2(72)/proviso[1] ✗ | 2(68) ✗ | paid-up share capital limit for a small company |
| 2(85)(ii) | ✓ | ✓ | ✓ | turnover limit for a small company |
| 96(1)/proviso[1] | 96(1)/proviso[3] ✗ | ✓ | ✓ | by when must the first AGM be held |
| 2(87) | ✓ | ✓ | ✓ | definition of a subsidiary company |
| 2(85) | ✓ | ✓ | ✓ | definition of a small company |
| 2(42) | 2(44) ✗ | ✓ | ✓ | definition of a foreign company |
| 2(68) | 2(71)/proviso[1] ✗ | ✓ | 2(71)/proviso[1] ✗ | definition of a private company |
| 2(71) | 2(85) ✗ | ✓ | 2(85) ✗ | definition of a public company |
| 2(45) / 2(52) / 2(62) / 2(57) / 2(43) | ✓ | ✓ | ✓ | five further definitions |

### Why BM25 fails where it fails — a lexical trap, not a lexical gap

Every BM25 miss is the same defect. The wrongly-ranked chunk contains the queried term
in a **negating or referential** use:

- `2(71)/proviso[1]` — *"a company which is a subsidiary of a company, **not being a
  private company**, shall be deemed to be public company…"* — ranked 1 for "the
  definition of a private company".
- `2(85)` — *"'small company' means a company, **other than a public company**,--"* —
  ranked 1 for "the definition of a public company".

BM25 sees the term and scores it. It has no representation of the fact that the chunk
is *about* something else and mentions the term only to exclude it. Dense does, and
puts the true defining clause at rank 1 in both cases.

This is why the error sets are nested rather than disjoint. On surface 1 the two
retrievers disagreed because long, topically distinct sections give lexical overlap and
semantic similarity genuinely independent evidence. Within one section the candidates
share the section's whole vocabulary, and the discriminating evidence is not *whether*
a term appears but *how it is used*. That is a distinction BM25 structurally cannot
make and dense can. So dense does not merely add signal here — it **dominates**, and
domination is precisely the condition under which fusion cannot help.

### Why fusion actively loses two cases

RRF's flat top is the mechanism, working exactly as designed and producing the wrong
answer because one of its two inputs is untrustworthy:

| question | expected chunk (bm25 rank, dense rank) → RRF | fusion's pick (bm25, dense) → RRF |
|---|---|---|
| definition of a private company | 2(68) (3, 1) → 0.032266 | 2(71)/proviso[1] (**1**, 2) → 0.032522 |
| definition of a public company | 2(71) (4, 1) → 0.032018 | 2(85) (**1**, 3) → 0.032266 |

k=60 is chosen so that "agreement across retrievers outweighs confidence within one".
That is the right trade when both retrievers are comparably reliable. When one is
strictly worse, it is exactly backwards: dense's rank-1 is out-voted by BM25's
confidently-wrong rank-1, and the margin is ~0.8% — the two candidates are separated by
a hair, and the hair falls the wrong way. Fusion loses these by design, not by accident.

Fusion gains 2 over BM25 and loses 2 against dense. It gains **nothing** over dense
(`fusion_gained` vs dense = ∅).

Tuning k would fix these two cases. **It was not tuned and must not be.** k=60 is the
published Cormack/Clarke/Buettcher default, run once. Fitting k against 13 cases would
turn the eval into a training set and make the resulting number meaningless — and it
would be fitting a fusion weight to compensate for the fact that fusion is the wrong
tool here, which is the wrong repair regardless.

### The one case neither gets

"the paid-up share capital limit for a small company" → expected `2(85)(i)`. BM25 ranks
it 7th (it prefers `2(68)`, and `2(64)` — the *definition of* paid-up capital — at 3).
Dense ranks it 2nd, preferring `2(72)/proviso[1]`. This is the failure the eval's own
docstring already predicted: a question whose terms are the *subject* of another
definition elsewhere in s.2. Note dense still has it at rank 2, so a reranker or an
n>1 candidate pool would recover it; a top-1 selector does not.

## Verdict

**Do not adopt RRF fusion for within-section chunk retrieval.** The cross-section win
does not transfer, and the reason is measurable rather than incidental: fusion's
precondition — complementary error sets — is absent here. `only_bm25 = 0`. Fusion
scores between its two inputs because that is what fusion does when one input dominates
the other, and on this eval it is strictly worse than simply using the better retriever.

**Dense over structural chunks is the promising direction, and it is not yet
adoptable.** 0.92 vs 0.62 is a large gap, but:

1. It rests on **13 cases**, of which **10 are one easy template**. The evidence on the
   hard, genuinely structural cases is **3 cases**.
2. Adopting it makes `sentence_transformers` + `torch` a hard runtime dependency of the
   *shipped* within-section path. Today they are dependencies of an *experiment*.
   `chunk_retrieval`'s docstring records the standing decision: retrieval ships on
   BM25, and the embedding dependency is revisited "only if real usage shows 0.62 is
   not enough". 13 cases is not real usage.
3. Dense refuses rather than degrades (by construction), so a machine without the
   cached model would take the within-section path from "worse" to "unavailable".

**Recommended next action** — the blocker is the eval, not the ranker. Grow the
scoreable set beyond the definition template: more proviso-selection and limb-selection
cases across several sections, derived structurally (as the definition cases were,
programmatically from the text's own layout) so no legal judgement is smuggled in.
Re-measure dense against BM25 on that set. If the gap holds on 30+ cases weighted
toward non-definition questions, adopt dense — alone, not fused — with an explicit
BM25 fallback path that is *labelled* degraded rather than silent.

The three NEEDS_LAWYER cases remain the H-B ask and are unchanged by any of this.

## Status of claims in this document

- BM25 0.62 / dense 0.92 / fusion 0.77 on 13 scoreable cases: **MEASURED**, reproducible
  by the command at the top.
- Error sets nested (`only_bm25 = 0`): **MEASURED**.
- The lexical-trap explanation for BM25's misses: **MEASURED** for the two quoted
  chunks (text reproduced above); **inferred** as the general mechanism.
- "Dense would hold up on a larger eval": **UNVERIFIED**. Not claimed.
- Any statement about production within-section accuracy: **UNVERIFIED**. This is a
  13-case internal measurement, not a production accuracy figure.
