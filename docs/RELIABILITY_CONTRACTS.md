# Reliability contracts

Behaviours other code may rely on, and the reasoning that produced them. Each is enforced by a test;
none is a convention.

## 1. A non-admitted provision can never yield DOES_NOT_APPLY

`checker/assessment.py`. "This does not apply to you" closes a question. "I could not assess this"
says the question is open and why. To a lawyer those are **opposite answers**, and a system that
confuses them tells users a provision is irrelevant when the truth is that it could not read the law.

Enforced in `Assessment.__post_init__`, not in `assess()`. Hand-constructing
`Assessment(key, WITHHELD, DOES_NOT_APPLY, …)` raises. A rule enforced only on the happy path is a
convention; one enforced at construction is an invariant.

Verified by **exhaustive enumeration** — 252 combinations of provision status × facts × blocking
sources × conflict × obligation, zero violations, with `DOES_NOT_APPLY` still reachable so the check
is not vacuous. Three examples would not have established this.

**Live consequence:** s.16 carries pre-amendment text (SD-002) and is SUSPENDED. Told
`facts_established=False` — the input that most tempts the wrong answer — it returns
`NOT_ASSESSABLE`, not `DOES_NOT_APPLY`.

## 2. Duplicate claim ids are order-independent

`checker/model_adapter.py`. Two claims sharing an id used to resolve first-wins, which made this
possible:

```
c1: "Board approval is required."
c1: "No approval is required."
```

The first survived — not because it was better supported, but because the model emitted it first.
An answer chosen by emission order is an answer chosen by accident.

**Contract:**
- a claim id is an identity key, not a display label; `1` and `"1"` collide after canonicalisation
- when an id repeats, **every** claim carrying it is rejected, the first copy included
- uniquely-identified claims in the same response survive — one malformed pair must not discard good work
- `DUPLICATE_CLAIM_ID` names the offending id; each rejection is recorded in `rejected_claims`
- raw model output is preserved verbatim, so nothing is lost
- with no substantive claim left, `APPLIES`/`DOES_NOT_APPLY` is downgraded to `INSUFFICIENT_EVIDENCE`

A duplicate id no longer changes the answer — it removes it.

## 3. The lexical verifier does not establish entailment

`checker/claim_verifier.py`. The lexical path tops out at **`LEXICAL_CANDIDATE`** and
`establishes_support()` is False for it. `SUPPORTED` is reserved for a verdict an entailment checker
has confirmed, and **nothing in this repo can produce one**.

That is not pessimism. `corpus/benchmark/entailment_v1.json` holds four claims about s.173 and the
checker distinguishes **none** of them:

| | Claim | Gold | Coverage |
|---|---|---|---|
| e01 | restates the provision | SUPPORTED | 1.000 |
| e02 | invents a Registrar filing duty | UNSUPPORTED | 0.667 |
| e03 | inverts the obligation | UNSUPPORTED | 0.800 |
| e04 | thirty days → **ninety** days | UNSUPPORTED | **1.000** |

e04 settles it: "ninety" appears elsewhere in s.173, so every distinctive term of a **false statement
of law** is present and coverage is perfect. No threshold separates e01 from e04 because nothing is
missing from either.

**Agreement with ground truth is 0/4, and the zero is the point.** It scored 1/4 before the relabel
by getting e01 "right" — while grading e01 and e04 identically. That was a label attached to a coin
flip. 0/4 states what the checker establishes about entailment: nothing.

Its legitimate jobs remain triage, obvious-mismatch detection, and a cheap pre-filter.

## 4. Nothing a model returns may crash the caller

`run()` fails closed to `INSUFFICIENT_EVIDENCE` on any parse failure, including type confusion —
five shapes covered in `checker/redteam.py`. `_parse` still raises; the split is deliberate, keeping
diagnostic precision inside while the boundary degrades safely.

Found by red-teaming: three type-confusion inputs previously escaped as uncaught exceptions, in the
one component whose output is untrusted by definition.

## 5. Failures are attributed to a stage, and to a KIND

`checker/attribution.py`. A whole-pipeline accuracy number cannot say which stage broke, and the
remedies are opposite: a provision never retrieved is a retrieval problem no prompt change fixes;
one retrieved, admitted and served but never cited is a generation problem no retrieval work fixes.

Stages: `RETRIEVED → ADMITTED → SERVED → CITED → GROUNDED`, monotonic and enforced at construction —
a ladder reporting CITED while SERVED failed describes something impossible.

Four outcome classes, kept apart from the stages on purpose:

| Class | Meaning |
|---|---|
| `PIPELINE_DEFECT` | our code is wrong; go fix it |
| `MODEL_FAILURE_CAUGHT` | the model misbehaved and a guard stopped it — working as designed |
| `CORRECT_REFUSAL` | we declined deliberately; no answer, and that is right |
| `COMPLETE` | an answer came out |

An earlier version had a single `system_behaved_correctly` boolean, and it reported
`GROUNDING_UNAVAILABLE` as **False** — implying a defect when the system had correctly declined to
claim grounding it cannot establish. Collapsing "go fix this" and "produced no answer" into one flag
makes the metric wrong in both directions: it panics about working safety behaviour, and it would
congratulate a system that answers nothing. `is_defect` and `produced_result` are now separate.

**Current reading:** all 7 frozen benchmark provisions attribute to `GROUNDING_UNAVAILABLE` /
`CORRECT_REFUSAL`. Nothing is broken; nothing is answered. That is the honest state of a system with
no entailment checker.

## 6. Withheld material is reported, never silently dropped

A relevant-but-unadmitted Rule produces a notice saying it exists and is not admitted. Silence and
"no such rule exists" are indistinguishable to a reader, and one of them is false.
