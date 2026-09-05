# Loop runbook — push readiness, then negative paraphrase candidates

    pattern : sequential
    mode    : safe
    started : 2026-09-03

## Stop condition

1. A push manifest exists naming branch, head, file counts and what changed.
2. No personal field appears in any distributable benchmark file.
3. The .github/workflows change is confirmed intentional and its content read.
4. The release snapshot verifies.
5. 15-25 negative paraphrase candidates exist, each with source, defect type,
   and the specific statutory words the claim breaks.
6. Every candidate is PENDING_REVIEW with proposed_label NOT_ENTAILED. NONE is
   promoted, because self-certifying a label is the failure F4 just closed.
7. Suite green.

## Out of scope

- Promoting any candidate. That needs the second reviewer.
- Any accuracy claim from the enlarged bucket.
