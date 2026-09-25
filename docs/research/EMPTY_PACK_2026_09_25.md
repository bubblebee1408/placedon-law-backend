# One response for four different situations

Found 2026-09-25 by `eval/goldset/`, immediately after adding the fourteen
**off-topic** entries the gold set had been missing.

## The measurement

```
refused-rightly (of those it SHOULD refuse):  9/14  ->  9/28
  --- HELD OUT (never tuned against) ---
  refused-rightly:                            0/6
```

Fourteen questions that are **not about Indian corporate law at all** were added.
Not one was refused. Held-out: zero of six.

## What actually happens

```
state=partial  confirmed=[]  not_confirmed=['pack_missing']   "How long should I boil eggs for breakfast?"
state=partial  confirmed=[]  not_confirmed=['pack_missing']   "What is the capital of France?"
state=partial  confirmed=[]  not_confirmed=['pack_missing']   "What is the GST rate on consulting services?"
state=partial  confirmed=[]  not_confirmed=['pack_missing']   "Delaware requirements for incorporating an LLC?"
state=partial  confirmed=[]  not_confirmed=['pack_missing']   "Do we need consent before sharing employee data…"  (DPDP, not held)
state=partial  confirmed=[]  not_confirmed=['pack_missing']   "Within how many days of the AGM must the annual
                                                               return be filed?"  (s.92 — HELD, retrieval miss)
```

**Byte-identical.** `state: "partial"` with an empty pack is this system's universal
"I have nothing", and it is returned for four situations a lawyer must be able to
tell apart:

| Situation | What the lawyer needs to hear | What they get |
|---|---|---|
| Body of law not held (FEMA, DPDP) | *"Not held. Here is what it covers and what we would have to acquire."* | empty pack |
| Held law, retrieval missed it (s.92, s.177) | *"We hold this. We could not find it — try rephrasing."* | empty pack |
| Not a legal question (boiling eggs) | *"That is not a question this system answers."* | empty pack |
| Right subject, wrong jurisdiction (Delaware) | *"Indian corporate law only."* | empty pack |

`CLAUDE.md`, on the eight declared-but-unheld bodies:

> *"…an **active refusal** — a question there is answered with the body of law, what
> it covers, and what we would have to acquire. **Never with silence, because silence
> would read as 'no obligation found'.**"*

This is that silence, and it is the default for everything the system cannot answer.

## Why this matters more than the retrieval defect

`RETRIEVAL_DEFECT_2026_09_25.md` found that natural questions lose their
correctly-ranked top hit. That is a bad failure. **This is the failure that makes it
invisible.** If a retrieval miss and an out-of-scope body produced different
responses, a lawyer would report "it can't find section 92" and the defect would have
surfaced in a week. Because they are identical, both arrive as a shrug, and a shrug
teaches the user that the product does not know much — never that it has a bug.

It also makes the gold set's own numbers soft: "refused" and "failed to retrieve" are
the same observable, so the two denominators are measuring one thing wearing two
labels.

## What is NOT wrong

**No fabrication. Anywhere.** Across 14 off-topic questions, 9 out-of-scope ones and
40 adversarial ones, the engine has never invented a provision, a rule or a citation.
The empty pack is *honest about holding nothing*. This is a defect of expression, not
of integrity — and the distinction is the whole difference between "unhelpful" and
"dangerous".

**An explicit refusal path exists and works.** All four prompt-injection attempts
returned `out_of_scope`, and so did all seven questions that named an unheld statute.
`checker/ask_scope.py` produces a proper refusal — it is simply only reachable by
naming the Act or its regulator.

## Honest caveat on the number

9/28 depends on scoring "empty pack" as *not a refusal*. That is a judgement, and it
is the one `CLAUDE.md` requires: a refusal that does not name the body of law and say
what is missing is not the active refusal the product promises. A looser reading
would score these as refusals and report ~23/28 — which is exactly the flattering
number this gold set exists to refuse.

## What would fix it

Not a model. The engine already knows which case it is in; it simply does not say:

- `ask_scope` returns a `Reading` with `body=None` — *"no declared body matched"*
- retrieval returns `ROUTE_ABSTAIN` with an empty pack — *"searched, found nothing"*
- `search()` returns `[]` after clearing MIN_COVER — *"nothing cleared the bar"*

Three distinguishable states collapsing into one output. A typed refusal reason on
the response — naming which of the four situations occurred — is a small change to
the envelope and needs no new capability. It belongs with `PLAN_18` §2.4.1's refusal
codes, which already enumerate `OUT_OF_SCOPE` and `CONTEXT_INSUFFICIENT` as separate
things.

**Not attempted here.** The finding is the deliverable, and the envelope is a
contract (`placedon.ask/0`) with a renderer and fixtures downstream of it.

## Method note

These fourteen entries exist because a retrieval fix scored 12/19 → 15/19 on this
gold set and was reverted after `text_search.py`'s own suite caught it breaking
precision. The gold set had fourteen refusal entries and **every one was about
another body of Indian law** — nothing that was not law at all. It could not see the
regression it was being used to justify.

A `DEV`/`HELDOUT` split was added at the same time. Six of the fourteen are held out
and were not consulted while writing any fix. They currently score 0/6, which is the
honest number.
