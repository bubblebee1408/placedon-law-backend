# Temporal engine — boundary proof

**Run:** 26 Aug 2026 · `scripts/prove_temporal.py`

## Result

| | |
|---|---|
| Sections | s.177, s.447, s.35 |
| Boundaries exercised | 6 |
| Passing | **6/6** |

```
ok   s.177    2015-12-14  in-force 0->1  text CHANGED  EXACT/EXACT  Act 21 of 2015
ok   s.177    2018-05-07  in-force 1->3  text CHANGED  EXACT/EXACT  Act 1 of 2018
ok   s.447    2018-02-09  in-force 0->2  text CHANGED  EXACT/EXACT  Act 1 of 2018
ok   s.447    2018-11-02  in-force 2->3  text CHANGED  EXACT/EXACT  Act 22 of 2019
ok   s.35     2018-02-09  in-force 0->1  text CHANGED  EXACT/EXACT  Act 1 of 2018
ok   s.35     2019-08-15  in-force 1->2  text CHANGED  EXACT/EXACT  Act 22 of 2019
```

## What each boundary asserts

For an amendment effective from D:

- **D-1** — not in force
- **D** — in force (*"with effect from D"* includes D)
- **D+1** — still in force
- **the reconstructed text at D-1 differs from the text at D**

The last is the assertion that matters. Without it, an engine returning the
current text for every date passes every ordering check and reconstructs
nothing. The off-by-one is not academic either: `wef < target` instead of
`wef <= target` would make every section one day stale, invisibly, on every date
except the boundary itself.

Also pinned: a date before commencement ABSTAINS rather than guessing; a
far-future date matches the last amendment date; the in-force count never
decreases as the date advances.

## Why these three sections reconstruct EXACT

Two different foundations, and they are not equally strong:

| Operation | Count | How the earlier text is known |
|---|---|---|
| **Inserted** | 5 | By **deletion** — remove the span. Nothing is quoted, nothing guessed |
| Substituted | 3 | The footnote quotes the prior wording. Single-sourced |

The insertion case is the stronger claim: reversing an insertion needs no
external witness at all. The substitution case rests on India Code's own
footnote, and only 24 such wordings anywhere in the corpus have been
independently corroborated (`docs/CORROBORATION.md`).

None of these three sections' prior wordings could be corroborated: the only
qualifying one rests on Act 22 of 2019, which Indian Kanoon does not host.

## What this does not establish

That the reconstructed text is what the Act actually said. EXACT means every
in-force span is **recoverable from the source we hold** — a statement about
recoverability, not about truth.

Section-level reconstruction remains unverified against an independent source
for substituted spans. Insertions are a different matter and are sound.

## Correction to SD-003, and its effect

The first version of this document reported "120 unbalanced spans" in India Code.
That was wrong. Classified by cause, 42 of the 121 were **our own regex** —
India Code writes `<sup>2</sup><b>[` as freely as `<sup>1</sup>[`, and the
pattern allowed only whitespace between marker and bracket. Fixing it recovered
41 spans and moved sections EXACT on both sides from **45 to 83**.

| (before, on-date) fidelity | was | now |
|---|---:|---:|
| EXACT / EXACT | 45 | **83** |
| PARTIAL / EXACT | 118 | 80 |
| PARTIAL / PARTIAL | 41 | 41 |

Genuine India Code defects: **10 spans**, not 120. Five open and never close
(s.96 among them), five name a marker that appears nowhere in the content.

The 69 spans with no bracket are not defects at all: 61 are omissions, where the
marker points at where text used to be and there is nothing to bracket. Their
prior wording cannot come from India Code at any price — only from the amending
Act.

## Scope limit worth stating plainly

**s.96 still cannot be reconstructed before 13 June 2018.** It is one of the
five genuinely unbalanced spans: one `[` after the marker, zero `]` thereafter.
The engine refuses rather than guessing, and a test pins that refusal so it is
not quietly "fixed" later.

The remaining PARTIALs are dominated by **omissions**, which no parser fix can
reach: the text is gone from the consolidation, so only the amending Act can
supply it. That is the genuine witness task, and it is unstarted.
