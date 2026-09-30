# The retriever answers the statute's vocabulary, not a lawyer's

Found 2026-09-25 by the gold set (`eval/goldset/`), one hour after it was built.
This is the first *accuracy* defect this repository has ever measured, as opposed
to asserted.

## How it surfaced

Nineteen MECHANICAL entries were added over **held** law — s.173, s.149, s.177,
s.96, s.92, s.203, s.184, s.164, s.185, s.188. Each expectation was derived from
corpus text and **verified present before the entry was written**; two candidate
phrases were rejected for not being in the held text at all (`"resident in India"`
in s.149, `"prior approval of the company by a resolution"` in s.188).

```
answered-correctly (of those it SHOULD answer): 12/19
refused-rightly    (of those it SHOULD refuse):  9/14
```

Seven failures on law the system **holds**, all of the same shape: *the governing
provision never reached the evidence pack.* Not the wrong section — **nothing**.

## The mechanism — CORRECTED

An earlier version of this document said `search` is **conjunctive**. **That was
wrong**, and the correction matters because it changes what the fix must do. The
measurement below replaced the guess.

`cover` is the share of the **query's** IDF mass a record accounts for, gated at
`MIN_COVER = 0.50`. So the bar rises with the LENGTH of the question — and a natural
question is mostly words the drafter of an Act never uses.

```
"audit committee"                                     s.177  cover=1.000  score=2.400  PASS
"How many directors must sit on the audit committee?" s.177  cover=0.377  score=0.819  CUT
"annual return filing"                                s.92   cover=1.000  PASS
"Within how many days of the AGM must the annual…"    s.92   cover=0.441  score=0.737  CUT
```

**The ranking was never wrong.** s.177 and s.92 are the top-scoring records in both
phrasings, comfortably above `SCORE_FLOOR`. The cover gate throws away a
correctly-ranked top hit because the asker used more words than the statute did.

Compounding it: `_idf` gives a term no section contains the **maximum** weight
(6.835) — deliberately, so nonsense queries return nothing. But "sit" then outweighs
"audit" (2.903) and "committee" (3.074) combined. A word the corpus has never seen is
treated as the most important thing in the question.

The original observation — that adding one unseen word can zero a query — is real.
Calling it "conjunctive" was not.

```
"audit committee"                                    3 hits   (s.177 top)
"audit committee sit"                                0 hits   <- "sit" is not in the Act
"How many directors must sit on the audit committee?" 0 hits

"annual return"                                      3 hits   (s.92 top)
"AGM"                                                0 hits   <- the Act says
                                                              "annual general meeting"
"annual return AGM"                                  0 hits
"annual general meeting annual return"               3 hits
```

The query does not need to be badly formed. It needs **one word the drafter of the
Act did not use.**

## The size of it

Twenty-two terms an Indian corporate lawyer types every day:

| Retrieves nothing | Retrieves |
|---|---|
| AGM · EGM · MD · CS · CFO · KMP · RPT · MOA · AOA · CIN · DIN · ROC · NCLT · "AGM notice" · "RPT approval" · "MD appointment" · "DIN application" · "ROC filing" · "NCLT petition" | "board meeting" · "related party" · "independent director" |

**19 of 22.** Every standard abbreviation in the practice returns zero results.

This is not a ranking problem to be tuned. The statute is drafted in full words and
never abbreviates; practitioners abbreviate almost everything. The corpus and the
user share a subject and not a vocabulary.

## Two independent defects, and they compound

1. **Conjunctive semantics.** One out-of-vocabulary token drops recall to zero
   rather than degrading it. BM25 is a *ranking* function over a disjunctive
   candidate set; used as an AND filter it cannot rank what it has already excluded.
2. **No abbreviation vocabulary.** Nothing maps `AGM -> annual general meeting`,
   `RPT -> related party transaction`, `KMP -> key managerial personnel`.

Either alone is survivable. Together, the common case — a lawyer typing an
abbreviation inside a question — fails completely.

## Why this is worse than a wrong answer

A zero-hit retrieval does not surface as an error. It becomes:

```json
{"state": "partial", "confirmed": [],
 "not_confirmed": [{"kind": "pack_missing",
                    "detail": "No provision was retrieved at all. This pack is empty."}]}
```

Which is the same output the engine produces for **law it does not hold at all**
(`GOLDSET_FIRST_RUN_2026_09_25.md`). So a lawyer asking a perfectly answerable
question about the Companies Act — in their own words — receives a response
indistinguishable from "this body of law is outside our scope."

`CLAUDE.md`: *"Never with silence, because silence would read as 'no obligation
found'."* This is that silence, arriving on **held** law, which is the one place the
product claims to be strong.

## Why 196 suites never saw it

Every retrieval test in the repository was written by someone reading the section at
the time, using the section's own words. `"audit committee composition"` passes.
`"How many directors must sit on the audit committee?"` does not, and nobody had
asked it that way before today.

## Not fixed here

The finding is the deliverable. Three candidate fixes, none obviously right, and the
choice is a measurement not a preference — which is now possible, because the gold
set can score all three:

- **Disjunctive retrieval with BM25 ranking.** The standard construction. Risk:
  recall rises and precision falls; the sufficiency gate (PLAN_17 M7) is what should
  absorb that, and it does not exist yet.
- **A declared abbreviation vocabulary.** Deterministic, auditable, and small —
  perhaps 40 terms cover most of the practice. It is also an editorial artefact
  someone must own and keep current; a wrong expansion is a silent mis-retrieval.
- **Query relaxation on zero hits.** Retry dropping out-of-vocabulary tokens, and
  SAY that the query was relaxed. Preserves today's precision for queries that
  already work.

The third is the only one that cannot make a currently-passing query worse, and it
is the only one that reports what it did. That is an argument for doing it first,
not for doing it alone.

**Whatever is chosen, `state: partial` with an empty pack must stop being the
response to an answerable question.** That much is already the stated rule.

## Status

No accuracy figure is claimed. 12/19 is a mechanical self-consistency measure at
n=19, where the observable lattice is 0.053 wide; the gold set prints the count and
the interval and withholds the rate, which is correct. Human labels: **0**. PLAN_16
C1 needs 59.

---

# The fix was attempted, measured, and REVERTED

Same day, immediately after the finding. Recorded because the failure is more useful
than the finding.

## What was tried

Measure `cover` over **matchable** terms only — those the corpus vocabulary actually
contains — and report the rest as `ignored_terms` rather than dropping them silently.
The reasoning: a term no record contains is mass no record can ever earn, so leaving
it in the denominator does not make the gate stricter, it makes it unreachable.

## It worked, on the metric it was built for

```
gold set, should-answer:   12/19  ->  15/19
gold set, should-refuse:    9/14  ->   9/14   (no regression)
```

Three of the seven held-law failures fixed; nothing that passed stopped passing; and
`search("xyzzy plugh frobnitz")` still returned `[]`.

## And it was wrong

`checker/text_search.py`'s own suite caught it in seconds — **four assertions that
existed before any of this work**:

```
[FAIL] nonsense 'how do I renew my passport'      -> expected [], got ['73']
[FAIL] nonsense 'best time to visit Goa'          -> expected [], got ['206','143',…]
[FAIL] nonsense 'python list comprehension'       -> expected [], got ['285','66',…]
[FAIL] nonsense 'what is the capital of France'   -> expected [], got ['378ZB','2',…]
```

*"What is the capital of France"* retrieves, because **"capital" is a Companies Act
word.** The cover gate was doing two jobs at once — rejecting off-topic queries, and
(incidentally) rejecting long ones. The change removed both.

The gold set measured recall and was blind to this. The pre-existing suite measured
precision and was not. **Neither instrument alone would have been safe**, which is an
argument for the old tests, not against them.

## Why no threshold was tuned instead

The obvious next move is an absolute floor on matched IDF mass. Measured:

| should pass | | should fail | |
|---|---|---|---|
| audit committee question | 7.11 | renew my passport | 5.74 |
| AGM / annual return | 9.28 | best time to visit Goa | 5.44 |
| board meeting by VC | 9.26 | python list comprehension | 3.28 |
| | | capital of France | 1.98 |

A threshold near 6.5 separates them. **It was not adopted**, because it would have
been fitted to three positive and four negative examples — chosen *because* they are
the examples on hand. That is overfitting a gate to its own test set, and it is the
same move as scoring a system against labels a model wrote: a number that looks like
a measurement and is a memory of the data.

At n=7 no threshold here is knowledge. The gold set is the thing that makes this
decidable, and it needs to be bigger first.

## Status: finding OPEN, fix NOT applied

`checker/text_search.py` is unchanged and at 47/47. The gold set is back to its
baseline of 12/19 and 9/14. Nothing was shipped on the strength of a metric that
only looked at one side.

The next honest step is more gold-set entries — enough that a candidate fix can be
judged on data it was not chosen from — and a held-out split so the judging is real.
