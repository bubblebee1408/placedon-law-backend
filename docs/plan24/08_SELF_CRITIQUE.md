# 08: Self-critique — what would make each part worthless, and when to kill it

The same author wrote 00–07, so this is a limited check. A reviewer who did not write the plan
should repeat it.

## 1. Doubts about the plan as a whole

**"Is this another plan instead of a product?"** This is the ninth plan document in two weeks
(PLAN_16 through PLAN_24). The founder's local session said as much: "too much planning
relative to validated use."

- **The defence:** T0 is almost entirely finishing work, and its first prompt builds nothing
  new.
- **The kill:** if T0 has not exited within 3 weeks of this document, no new plan document is
  written until it has.

**"Does the learning loop have anything to learn from?"** Not today. There are 0 HUMAN labels.
Without H-001 and a pilot, T2 builds a flywheel with nothing on it.

- **The kill:** if T2 exits and 60 days later the labels table holds < 50 HUMAN rows, stop T3+
  and put all effort on getting reviewers.

**"Is the analytics ladder a way of saying yes to prediction without meaning it?"** Partly. It
is a way of saying yes to the parts that can be made honest (L1–L4) and a *conditional* yes to
L5.

- **The risk:** a gate built to be passed rarely invites pressure to loosen it.
- **The mitigation:** the gate in 04 §5 is committed *before* any data is seen, and changing
  it after seeing data counts as a failed pre-registration.

## 2. Doubts about specific claims

| Claim | Doubt | Status |
|---|---|---|
| "RAG beats fine-tuning for new knowledge" (Ovadia et al.) | Their setting is general knowledge-intensive QA, not Indian law. Results could differ for heavily structured statutes | [S]; the conclusion is also forced independently by PLAN_22 D1 (dating) and Carlini (leakage), so it does not rest on one paper |
| "Only 12 of 171 LJP papers forecast" | Figures from a search summary of the paper; PLAN_19 separately recorded ~7% | [S] + [V] in PLAN_19; consistent |
| NyayaAnumana ~90% F1 | Search-summary figure; task construction not read | Marked as not comparable (02 P5) |
| "NCLT is the forum that matters most" | [I]. In-house teams may care more about SEBI orders or HC writs | Validate in H-001's interview: ask which forum decisions they track |
| Scheme-timeline analytics is valuable to in-house counsel | [I], untested | Same interview. **Kill T6 if 3 of 3 interviewed counsel say they would not use it** |
| Tenant scorer thresholds (≥ 200 labels; ≥ 95% of ≥ 60) | Chosen, not derived | Replace with a derivation from the gate's n before T3 builds it |
| Judge-field scan is enough to keep L6 off | A bench id plus a date can re-identify a judge | The scan also covers bench-composition fields; aggregate at forum level by default (04 §3.2) |

## 3. What the plan might have missed

- **Access may be the whole game.** T5 and T6 both depend on someone else's terms (the
  CC-BY grant, NCLT). If either says no, those phases stop. They are not delayed. The paid
  fallback (the Indian Kanoon API) is excluded by the founder's free-only decision of
  2026-09-25.
- **The newest work is on an unmerged branch.** This plan was written against `main` and read
  the newer branch through `git show`. Some T0 items may already be closed there. Prompt 1's
  pre-flight step 4 checks this before doing anything.
- **"Top-tier firms only" pricing** is outside this plan. PLAN_20 targets mid-market in-house
  teams first, *under* Harvey. The founder's new framing ("exclusive, frontier") contradicts
  that staging, and the contradiction needs a business-strategist pass, not an engineering one.

## 4. What would falsify PLAN_24

1. In H-001, a practising professional says none of recall, scenario or forum statistics
   would change what they do.
2. After T2, reviewers' decisions turn out too inconsistent to use as labels, for example
   below 0.6 agreement between two reviewers on the same 50 items (Cohen's κ). Then "learning
   from reviewers" learns noise, and the loop needs adjudicated labels first.
3. T6's first real stratum cannot reach n = 30 for any Companies Act matter type at any single
   bench. Then forum statistics are too thin to show, and L3–L4 collapse to counts.
