# M13 — `checker/derivation.py`: the semiring already half-exists, and G0.5 does not block it

Architect record, 2026-09-26, for move 13 of
`.claude/plans/loop-twenty-moves-2026-09-26.md` (PLAN_19 G2.1). Before code, per §2.2.

## 0. G0.5 does NOT block this, and PLAN_19 says so

`docs/plan19/04_MATHS_AND_ALGORITHMS.md` §1 proposes a total order over
`provenance.STATES` and marks the `UNFETCHED_CORROBORATION` vs `INFERRED` question
**[OPEN]**, for a legal decision. It then says the thing that matters here:

> *"The algebra works for any total order. The legal meaning depends on which one is
> chosen."*

So the algebra is buildable now. **`provenance.EVIDENCE_ORDER` does not exist** (checked),
and this module will not create it — that is G0.5's output and a human's decision.

**Decision: `derivation` takes a `Lattice` as a parameter and declares no order of its
own.** The property tests then run over **randomly generated total orders**, which proves
the axioms hold for *any* order rather than for one guess. That is strictly stronger than
testing the proposed order, and it cannot be invalidated by whatever G0.5 decides.

## 1. Half the semiring already exists. Do not reimplement it

`checker/lattice.py` (free — last touched two weeks ago; importers:
`corpus_currency`, `calibration_contract`, `currency`, `staleness`) already provides:

```python
Lattice(name, states)            # a total order, declared best -> worst
  .rank(state)                   # raises LatticeError on an unknown state
  .worst_of(items, status_of)    # -> Verdict(state, witness)
```

`worst_of` **is** the semiring's ⊗ (AND, weakest link), including the witness and the
tie rule — *"ties resolve to the FIRST item at the worst rank, so a rollup over the same
inputs in the same order always names the same witness."* Reimplementing it in
`derivation.py` would be a second notion of composition, and the two would drift.

**What is missing is the dual: ⊕ (OR, strongest alternative).** Decision: add `best_of`
to `lattice.py` beside `worst_of`, not to `derivation.py`. It is the dual of a lattice
operation and belongs with its twin; putting it elsewhere means the next reader finds one
half and not the other. `lattice.py` has four importers and none of them gains behaviour
— `best_of` is additive.

## 2. Identities, and why empty is not an error

| | operation | identity | empty means |
|---|---|---|---|
| ⊗ AND | weakest link | `best` (⊤) | resting on no dependencies IS best — `worst_of` already returns `witness=None` and says so |
| ⊕ OR | strongest alternative | `worst` (⊥) | no alternative supports this at all |

`worst_of`'s docstring already argues the AND case: *"a thing resting on no dependencies
is genuinely at the best state, and returning `witness=None` says exactly that rather
than inventing a cause."* The OR case is the mirror and must not silently return `best`.

## 3. The same-value guard: OR over CONFLICTING values raises

`⊕` combines alternative *supports for the same claim*. Two sources that disagree about
the **value** are not alternatives — they are a conflict, and picking the better-evidenced
one would be laundering a contradiction into an answer.

So `evaluate` raises `SourceConflict` when alternatives carry different values, rather
than returning the strongest. `checker/provenance.py` already has the vocabulary for this
(`SOURCE_CONFLICT` appears in the register scripts' outcome set), and CLAUDE.md's rule is
explicit: *"Never repair a defective government source. Flag it, preserve it verbatim."*

## 4. What the property tests must actually prove

500 seeded cases each (PLAN_19 G2.1), over **random** total orders:

1. **Semiring axioms.** ⊕ and ⊗ associative and commutative; ⊗ distributes over ⊕;
   `best` is ⊗'s identity and `worst` is ⊕'s; `worst` annihilates ⊗.
2. **Lemma 2 — minimal witnesses.** Evaluating the minimal witness set gives the same
   result as the full DNF. This is the property that makes revocation re-evaluation
   rather than re-query, and it is the reason the module exists.
3. **Corollary 3 — monotonicity.** Improving any input cannot worsen the result.

**A random order is generated per case and the axioms asserted against it.** If an axiom
holds only for the proposed order, that is a defect in the algebra, not a fact about law.

## 5. The guard family, stated because it has four instances in two days

> A guard that tests for PRESENCE is not a guard that tests for CONTENT.

Concretely here:

- `rank()` already raises on an unknown state. `derivation` must **not** catch it and
  substitute a default — an unrecognised evidence word must stop the rollup, not become
  the weakest one silently.
- A derivation with **no** witnesses is not the same as one whose witnesses are all
  `UNRESOLVED`. The first has nothing to say; the second says something weak. They must
  not render alike.
- `evaluate` returns a `Verdict` carrying its witness, always. A verdict with no witness
  is unusable, which `rings.py` already says of its own violations.

## 6. Ring, and what is out of scope

Ring 1, registered in `rings.py`. It imports `lattice` and `provenance` — downward and
sideways. Pure: no clock, no network, no I/O, no model.

Out of scope: `provenance.EVIDENCE_ORDER` (G0.5, a human decision); the differential test
against every served obligation (move 14 — and **any diff stops the phase**, the old path
is not "fixed" to match); `scripts/revocation_report.py` (move 15).
