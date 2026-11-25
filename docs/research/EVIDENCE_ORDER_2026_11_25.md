# G0.5 Decision: Evidence Order

**Date:** 2026-11-25
**Decision by:** founder (via session instruction)

## The question

PLAN_19 G0.5 asks: is `UNFETCHED_CORROBORATION` (an inaccessible source reported to agree)
stronger than `INFERRED` (our own derivation from held text)?

## Decision

**INFERRED is stronger than UNFETCHED_CORROBORATION.**

## Total order (weakest → strongest)

```
RETRACTED < UNRESOLVED < UNFETCHED_CORROBORATION < INFERRED < CORROBORATED < VERIFIED
```

## Reasoning

1. **INFERRED** means this system derived a fact from text it holds and can re-derive on demand.
   The derivation is verifiable: anyone with the same corpus can run the same logic and check
   whether the conclusion follows. It is reproducible and auditable.

2. **UNFETCHED_CORROBORATION** means a source we cannot read is *reported* to agree with us.
   We cannot verify the report, we cannot read the source, and we cannot check whether the
   agreement is real or a stale cache of what used to be true. It is hearsay.

3. A verifiable derivation from held text is stronger evidence than an unverifiable report of
   agreement from an inaccessible source. The product's thesis — "the model may propose, the
   system must verify, the reviewer decides" — requires that verifiability outrank reputation.

4. Neither is SERVABLE. Both sit below the serving threshold (CORROBORATED, VERIFIED).
   The order matters for internal prioritisation, evidence-pack display, and deciding which
   claim to prefer when two claims about the same fact carry different states.

## Implementation

`checker/provenance.py`: `EVIDENCE_ORDER` tuple, `evidence_strength()`, `stronger()`, `weakest()`.
132/132 self-tests pass.
