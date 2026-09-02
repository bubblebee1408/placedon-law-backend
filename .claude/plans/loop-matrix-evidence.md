# Loop runbook — wire evidence into the compliance matrix

    pattern : sequential
    mode    : safe
    started : 2026-09-02
    branch  : engine/entailment

## Why

Stage 1 ships a matrix in which every applicable row reads
APPLIES_UNDETERMINED. That is honest — the register holds no meeting dates and
no notices, so it cannot say whether a duty was met. But it means the product
currently answers "this applies to you" and stops one step short of "and here
is where you stand", which is the sentence a practitioner actually wants.

The engines that CAN decide already exist and pass: `checker/s96_slice.py` and
`checker/s173_slice.py`. They are not connected to `checker/obligations.py`.
This loop connects them.

## Stop condition — all five, verified by tests

1. Evidence (AGM dates, board meeting dates) can be attached to a matrix build.
2. The s.96 row resolves to APPLIES_SATISFIED or APPLIES_NOT_SATISFIED when the
   supplied dates settle it, and stays APPLIES_UNDETERMINED when they do not.
3. The s.173 row does the same.
4. No row can reach APPLIES_SATISFIED without evidence. Asserted by a test that
   enumerates evidence-free profiles.
5. `scripts/run_tests.sh` is green and the web form accepts the evidence.

## Safety gates (mode: safe)

- Full suite green before each commit; the pre-commit hook enforces this.
- One logical change per commit.
- No new dependency. Stage 1 must still run with nothing installed.
- No row may claim compliance the evidence does not support — this is the
  failure mode the whole product exists to prevent, and it is gate 4.
- Refusals keep naming what is missing; an unresolved row must not silently
  become a satisfied one.

## Out of scope

- Document upload or extraction. Evidence is typed in at this stage.
- Any model call. Stage 1 stays model-free.
- New obligations beyond the three already registered.

## Monitor

    ./scripts/run_tests.sh
    PYTHONPATH=. python3 checker/obligations.py
    PYTHONPATH=. python3 scripts/serve_matrix.py   # http://127.0.0.1:8014
