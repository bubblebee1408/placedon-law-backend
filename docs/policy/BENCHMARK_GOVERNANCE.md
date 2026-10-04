# Benchmark remediation and governance

Written 2026-09-02, after promoting v3.

---

## 1. Executive decision

**v3 is promoted.** It was authorised and executed before this document was
written, so the decision this records is what governs the *next* one.

The promotion was safe on its mechanics: the live file is byte-identical to the
candidate that was reviewed and scored, v2 is archived and verifies, and the
adjudication naming all 21 changes was written before the promotion, not after.

It carries one governance gap, stated plainly rather than buried: **both label
corrections were adjudicated by a single non-lawyer reviewer.** The arithmetic
is unambiguous — on a three-director board one-third is 1 while the quorum is 2 —
but "unambiguous to me" is not the same as adjudicated. A second reviewer on
relabelled items is the first item in §8.

---

## 2. Current state

**What was wrong with v2.** Nineteen of its 69 pairs carried a source-span hash
that no longer matched the span the generator produced, and two of its gold
labels were wrong. It was internally consistent and externally stale.

**Why the gate certified nothing.** `evaluate_gate` scored
`entail_pairs_v2.all_pairs()` — a generator that rebuilds the pair set at import
time — while the manifest's SHA-256 protected `approved_pairs.jsonl`, a file the
gate never opened. The hash would have validated forever while the measured set
drifted underneath it. It had already drifted: 69 pairs and 22 ENTAILED
attested, 67 and 20 measured.

**Which past scores are invalid.**

| Reported | Status |
|---|---|
| FA 8 / F1 0.48 | generator-measured; no version |
| FA 2 / F1 0.51 | generator-measured; no version |
| FA 2 / F1 0.58 | generator-measured; **never measured v2** |
| **FA 2 / F1 0.62** | **v3-measured, spans hash-verified** |

Every figure this project has ever quoted before v3 was measured on a generator,
not on a versioned artifact. **F1 0.58 → 0.62 is not an improvement**; it is the
first number that measures anything nameable.

---

## 3. Evidence review

**The 19 span corrections.** Sixteen on s.96(1), whose premise had been
truncated at 400 characters with the cut landing inside the first proviso — so
the premise stopped before "nine months" while a pair labelled ENTAILED asserted
exactly that. The premise did not contain the evidence for its own label. Three
on s.174(3), whose pairs had been frozen against the s.174(1) span.

**The 2 label corrections.** `v2-p174-bind-0` and `-1`, both `ENTAILED →
INVALID_FIXTURE`. The premise reads, verbatim: *"The quorum … shall be one-third
of its total strength or two directors, whichever is higher."* Each claim states
one limb and omits the selector. On three directors, one-third is 1 and the
quorum is 2; on nine, two directors understates a quorum of 3. Both claims are
false on real boards.

**Why these are annotation defects, not model defects.** The provision is
correct in our corpus. The checker refuses both claims and is right to. Only the
labels were wrong. No code changed as a result of this adjudication — which is
the test that distinguishes an annotation defect from a regression.

`INVALID_FIXTURE` rather than `NOT_ENTAILED` because each states a *real*
binding in a misleading frame. Relabelling them negatives would teach the
checker that the quantity itself is wrong.

**Modules that read the frozen file:** `benchmark_v2_freeze`,
`promotion_preview`, `scoped_retraction`, `review_record`,
`benchmark_refreeze_request`. None pins a version — they all read *current*.
That is why versioning had to precede promotion, and it is a remaining weakness:
a module reading "current" cannot reproduce an old score.

---

## 4. Governance policy

**An immutable version** is a directory under `corpus/benchmark/versions/<id>/`
holding the pair file, its manifest, and `SHA256SUMS`. `archive()` refuses to
write over an existing version. `verify_archive()` detects any later alteration.

**A breaking change** is any of: a gold label moves; a pair is added; a pair is
removed. Each changes what the system is judged against.

**A non-breaking change** is a span correction alone. The question and the
answer are unchanged; only the evidence cited is corrected.

**Comparability is false** whenever a breaking change occurred, and
`Correction.comparable` computes this rather than leaving it to judgement. The
record then carries `why_not_comparable` in words a reader can act on.

**Adjudication requirements for a future label change:**

1. The premise quoted verbatim, not summarised.
2. The specific statutory words that defeat or support the claim.
3. A worked counter-example where the old label gives a wrong answer.
4. Whether the defect is in the source text, the annotation, or the checker.
   Only annotation defects may be fixed by relabelling.
5. **Two reviewers**, at least one of whom has read the provision. Not met for
   v3 and recorded as such.

---

## 5. Promotion checklist

Before promoting any future candidate:

- [ ] Prior version archived and `verify_archive()` clean
- [ ] Correction record written, every change carrying a reason
- [ ] Every label change adjudicated per §4, by two reviewers
- [ ] Candidate written to its version directory, live file untouched
- [ ] Gate scored against the candidate, every span hash verified
- [ ] `comparable_with_previous` computed and recorded
- [ ] Rollback copy of the live file taken
- [ ] Explicit human authorisation, quoted verbatim in the record
- [ ] Post-flight: live file byte-identical to the reviewed candidate
- [ ] Post-flight: prior archive still verifies
- [ ] Full suite green
- [ ] Promotion record written with both hashes

All twelve were satisfied for v3 except the two-reviewer requirement.

---

## 6. Metrics policy

Reported every time: false accepts (absolute count), F1, abstention rate,
per-bucket breakdown, and the majority-class baseline.

**F1 is `N/A`, never `0.00`, when a bucket has no positives.** F1 is defined
over positives; a bucket with none has nothing to find, so `0.00` reports an
arithmetic fact as a performance failure. `dropped_qualifier` reads `N/A` for
exactly this reason and its real signal — FA 0 — is sound.

**False accepts are meaningless when a bucket has no negatives**, and the render
says so. `paraphrase` shows `FA=0` and it is vacuous: there is nothing there to
falsely accept.

**Every public claim must name the benchmark version and the evaluator commit.**
A score without a version is not a result. The correct form is: *"FA 2, F1 0.62
on benchmark v3 (67 pairs, 5 sections), evaluator commit `<sha>`."*

---

## 7. Release and communication policy

**Internally:** "v3 corrects nineteen source spans and two gold labels. It is a
new baseline, not an improvement over v2."

**Never say:** "F1 improved from 0.58 to 0.62." Both because a label moved, and
because 0.58 was measured on a generator and never measured v2 at all.

**Safe for an investor or customer conversation:**

> The benchmark is 67 constructed pairs across five sections of one Act,
> reviewed by one non-lawyer. It measures internal consistency. It is not
> evidence of legal accuracy, and we have not made an accuracy claim.

**Not safe, in any framing:** any accuracy percentage; any comparison to a
competitor's benchmark; any characterisation of these buckets as coverage. Two
of three cannot measure what the gate claims — `dropped_qualifier` has no
positives, `paraphrase` no negatives, and the latter is permanent by
construction until the fixture schema changes.

---

## 8. Two-week execution plan

Benchmark first, then product.

| Day | Work |
|---|---|
| 1 | Second-reviewer pass on the two relabelled pairs. Record the adjudication whichever way it goes. |
| 2 | Version-pin the five modules that read *current*, so an old score is reproducible. |
| 3 | Fix F4 — the review record carries a reviewer's **label**, not their approval. Migrate the 15 human-judged records. |
| 4 | Author 6–8 genuine negatives for `paraphrase`, so the bucket can detect a false accept at all. |
| 5 | Re-freeze as v4 under the full §5 checklist, two reviewers. |
| 6 | **Push the backend repo.** 128 commits on one machine is the largest uninsured risk here. |
| 7–8 | Practitioner validation: the matrix and the kit in front of one Company Secretary. |
| 9–10 | Act on what they say. Expect it to reorder the backlog. |
| 11–14 | Resume obligations — s.177 audit committee, or whatever the practitioner named instead. |

Nothing before day 11 adds a feature. That is deliberate.

---

## 9. Risks

| Risk | If it bites |
|---|---|
| **Promoting too fast** | Already partly realised: v3 went live on a single reviewer's adjudication. Mitigation is day 1, retrospectively. |
| **Delaying too long** | The gate certifying nothing is a standstill on every accuracy statement, and a standstill has no natural end. Promoting was right; the checklist is what makes the *next* one safe. |
| **Single-reviewer adjudication** | The reviewer is a non-lawyer and the subject is law. On these two the arithmetic is checkable by anyone. On a harder pair it would not be, and the same process would produce the same confidence with none of the justification. |
| **Single-class buckets** | Two of three cannot measure their axis. `paraphrase` is permanently blind to false accepts *by construction* — `entail_pairs_v2.py:408` hardcodes `label=ENTAILED`, so more review cannot fix it. |
| **Version-blind readers** | Five modules read *current*. An old score cannot be reproduced today. |

---

## 10. Recommendation

1. **Second review of the two relabelled pairs.** Retrospective, and the only
   item that touches something already promoted.
2. **Push the backend.** 128 commits, one machine, no remote copy. This is the
   largest risk in the project and it is not a technical problem.
3. **Fix F4 and author negatives for `paraphrase`.** Until then a third of the
   gate is decorative.
4. **One practitioner.** The benchmark can say the checker is internally
   consistent. Only a Company Secretary can say whether the obligations,
   evidence fields and refusals match how the work is actually done.
5. **Then resume obligations**, in whatever order that conversation implies.

The promotion command is not repeated here, because it has already been run and
this document governs the next one.
