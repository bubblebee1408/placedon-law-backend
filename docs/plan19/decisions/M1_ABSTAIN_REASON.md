# M1 — Why one `abstain` covers four situations, and the additive field that separates them

Decision, 2026-09-26. Move 1 of `.claude/plans/loop-twenty-moves-2026-09-26.md`.
Written by the main session: the architect subagent verified the same ground and was
killed by the usage limit with "everything verified, writing the decision" as its last
line. Every claim below was re-checked directly, with the file and line.

## 1. The decision, in one sentence

Keep `evidence_pack.route` exactly as it is and add **one additive optional field,
`abstain_reason`**, set at the three `ROUTE_ABSTAIN` return sites in
`checker/retrieve.py`, because `route`'s values are pinned by a contract fixture and a
second field that nearly duplicates `route` would be two notions of truth.

## 2. Two corrections to the finding that motivated this move

Both mine, both published, both now withdrawn in
`docs/research/EMPTY_PACK_2026_09_25.md`.

**2.1 "Byte-identical" was too strong.** A field-by-field diff of the four cases shows
they differ in exactly one place: `evidence_pack.retrieval_query`, the question echoed
back. Everything else matches. An echo of the input is not a signal about the answer,
so the finding stands — but the word does not.

**2.2 A typed field already exists and is already served.**
`evidence_pack.route` (`checker/retrieve.py:42-44`: `exact` | `search` | `abstain`) is
in the payload, documented in `web/assistant/contract.md:123`. The earlier version of
this plan proposed a NEW top-level refusal field. That was designed against a wrong
premise. The gap is narrower: **one `abstain` value covers four situations**, and
`eval/goldset/run.py` was not reading the field at all (fixed in move 2, `3125a36`).

## 3. Why `route`'s values may not change

`scripts/assistant_contract.py:266` asserts, on a committed fixture:

```python
and emp.get("not_confirmed") and emp.get("evidence_pack", {}).get("route") == "abstain",
```

So `abstain` is a pinned value, not an implementation detail. `PLAN_17` M7 rule 1 —
*extend the `placedon.ask/0` contract additively, new optional fields only* — settles
the rest. A new field beside `route` it is.

## 4. The three states the code can already prove

All three reach `ROUTE_ABSTAIN` today and are indistinguishable in the payload.
Verified at `checker/retrieve.py`:

| Line | Situation | `abstain_reason` |
|---|---|---|
| 158 | A citation resolved to rows, and **admission withheld every one** | `HELD_NOT_ADMITTED` |
| 166 | `names_a_provision(query)` is true and the citation **cannot be resolved** — deliberately does not fall through to search | `CITATION_UNRESOLVED` |
| 174 | Search ran and **nothing cleared `MIN_COVER`/`SCORE_FLOOR`**, or admission withheld all of it | `NOTHING_RETRIEVED` |

`OUT_OF_SCOPE` is **not** in this table: `ask_scope` decides it before retrieval runs
(`web/assistant/contract.md` §6 D2), and `state: "out_of_scope"` already carries it.

## 5. What the engine CANNOT distinguish, and why no code is invented for it

**"Not a legal question at all" is not knowable here.** Compare:

```
"How long should I boil eggs for breakfast?"                        -> 0 hits
"Within how many days of the AGM must the annual return be filed?"  -> 0 hits  (s.92 IS held)
```

Both are `NOTHING_RETRIEVED`, and they are genuinely the same fact about the engine:
*we searched what we hold and found nothing.* Separating them needs a subject-matter
classifier — a model deciding scope — and `checker/scope.py` is deliberately the
authority (CLAUDE.md). **So `NOTHING_RETRIEVED` is honest and an `OFF_TOPIC` code
would be a lie with a clean interface.**

This is a narrowing of what this move was originally scoped to deliver, and it is the
right narrowing. The earlier plan text implied four distinguishable cases; the code
supports three.

## 6. Why PLAN_18 §2.4.1's vocabulary does not fit

`git show origin/main:docs/PLAN_18_TECHNICAL_DESIGN.md`, around line 240, lists eight
refusal codes. Checked: **none names "searched the held corpus and found nothing."**
`CONTEXT_INSUFFICIENT` belongs to a sufficiency gate that does not exist yet;
`PROVIDER_NOT_PERMITTED`, `BUDGET_EXHAUSTED` and `CLAUSE_UNTRACED` belong to the M7
pipeline. That table is for the pipeline, not for today's engine, and using its names
here would imply machinery we do not have.

## 7. `web/assistant/contract.md` §6 D4 was more nearly right than I credited

D4 already requires that each thing a `partial` says about itself is used *"only where
it is true"*, and already names `NOTHING_DECIDED`, `TEXT_NO_FACTS`, `TEXT_NO_ROW`,
`LEXICAL`, `FACTS_NOT_APPLIED`, `UNRESTED`. The defect is narrower than "there is no
vocabulary": **`NOTHING_DECIDED` is doing the work of several different facts**, and
nothing separates "we do not hold this body of law" from "we hold it and did not find
it".

## 8. Implementation, and the one thing to be careful of

1. `checker/retrieve.py` — three constants; set at lines 158, 166, 174.
2. `checker/evidence_pack.py` — `EvidencePack` gains `abstain_reason: str = ""`, and
   `build_pack` an optional keyword. **Empty string, never None**, so the field's type
   never varies. `""` when the route is not `abstain`.
3. `checker/ask_read.py:63` `_pack_summary` — add the key. This is the one place the
   served dict is assembled.
4. `web/assistant/contract.md:123` — document the field additively.
5. `eval/goldset/run.py` — read it, so move 2's tripwire becomes specific.

**The care point:** `scripts/assistant_contract.py` rebuilds every fixture from the
route's own `answer()`, so fixtures will legitimately gain the key. That is a real
fixture diff and must be reviewed, not regenerated blindly — the whole point of that
file is that a fixture cannot say something the route would not.

## 9. What this does not do

It does not change `route`. It does not change any `state`. It adds no model, no
dependency, no ring. It does not claim to know whether a question was about law.
