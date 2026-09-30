# Retrieval ranking bake-off — 2026-09-30

**Result: no candidate won. The control ranker stays.** One pass, no second round.

Reproduce: `PYTHONPATH=. python3 scripts/retrieval_bakeoff.py`

## The rule, fixed before the numbers

A candidate wins only if **all three** hold:

1. it breaks no dev answer row that passes today;
2. title recall@1 does not drop;
3. dev refusal leaks do not rise.

More than one winner → take the simplest. No winner → keep the control. The rule was written
into `scripts/retrieval_bakeoff.py` before the run, and its own tests prove it rejects for each
of the three reasons separately — a rule that cannot reject decides nothing.

## The table

| candidate | dev answer@5 | dev refusal leaks | title recall@1 | verdict |
|---|---|---|---|---|
| **a — control** | **12/13** | **3/17** | **452/464** | **kept** |
| b — BM25 length norm, b=0.25 | 10/13 | 1/17 | 452/464 | lose — breaks `held_s173_gap`, `held_s173_vc` |
| b — BM25 length norm, b=0.50 | 10/13 | 1/17 | 452/464 | lose — breaks `held_s173_gap`, `held_s173_vc` |
| b — BM25 length norm, b=0.75 | 10/13 | 1/17 | 452/464 | lose — breaks `held_s173_gap`, `held_s173_vc` |
| c — control + title prior (0.5) | 12/13 | 4/17 | 452/464 | lose — breaks `held_s203_cs`; leaks rise |

## What the numbers say

**(b) reproduced the existing finding, independently.** `checker/text_search.py` already
recorded that BM25's length prior was tried and removed:

> With b=0.6 the length prior pushed s.173 below s.146 for "can a director attend by video" —
> the correct answer lost to a section about auditors, purely for being long. Measured, then
> removed.

That was one question at one value of b. This pass tried three values on a different eval set
and broke **both** s.173 rows at every one of them. The original finding holds, and the reason
holds with it: in a statute, length tracks subject complexity rather than padding. s.173 is long
*because* board meetings are intricate, and a prior that reads length as verbosity will keep
demoting it.

**The trade (b) offers was real, and was refused.** It cut refusal leaks from 3/17 to 1/17 —
better precision, which is the other half of R1's problem. It cost two answer rows. Under the
rule, breaking a passing row disqualifies regardless of what is gained elsewhere, and the rule
was not going to be renegotiated after seeing the table. That is the whole value of fixing it
first.

It is worth saying plainly that this is a **trade, not a verdict on b's worth**: a future pass
with a precision metric weighted against recall could reach the opposite answer honestly. It
would need its own rule, fixed in advance, and a reason to value precision more than an
answered question.

**(c) gained one row and lost another.** Its answer count is unchanged at 12/13, which is
exactly why the rule names rows instead of counting them — a candidate that breaks
`held_s203_cs` and fixes something else would have passed a count-based test while changing
which questions the product can answer. It also raised leaks 3→4.

## Since (b) was not adopted

The instruction was that the docstring's reason for omitting length normalisation must be
answered in writing **if (b) is adopted**. It was not, so there is nothing to answer — the
docstring's reason was tested and it survived. The finding is now recorded beside it in
`checker/text_search.py` with the three b values, so the next person to reach for BM25's `b`
sees that it has been measured twice.

## What this is worth, stated plainly

Thirteen dev answer rows, seventeen dev refusal rows, 464 headings. **Thirteen rows cannot
support an accuracy claim and none is made here.** This table says which candidate did not
break what, on this set, on this day. It is not a measurement of retrieval quality, and a
candidate that "wins" on thirteen rows has won very little.

**The held-out split was neither run nor read.** H0 spent its one run; a ranking tuned against
held-out rows would destroy the only unbiased number this project has.

`held_s173_first` — *"When must a newly incorporated company hold its first board meeting?"* —
remains the single dev miss. It loses to s.149, whose body happens to contain all seven query
terms (cover 1.000) while s.173 ranks sixth. Neither candidate here addressed it: (b) made it
worse and (c) did not move it. It stays open.
