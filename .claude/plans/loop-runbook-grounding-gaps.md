# Loop Runbook — close the spec gaps in the grounding layer

**Pattern:** sequential · **Mode:** safe · **Started:** 2026-08-21

## Not a rebuild

`claim_schema`, `model_adapter`, `claim_verifier` and `baseline_eval` shipped in `13a6bde` and are
green. Re-implementing them against a spec that describes them would burn the turn producing what
already exists. Only the genuine deltas are in scope.

## The five gaps

| # | Gap | Why it matters |
|---|---|---|
| 1 | Malformed model output **raises** instead of failing closed | **A defect.** An exception crashes the caller; abstention degrades safely. Fail closed to `INSUFFICIENT_EVIDENCE` + `MODEL_OUTPUT_PARSE_FAILURE`. |
| 2 | `INVALID_CITATION` folded into `UNSUPPORTED` | "Cited something that does not exist" and "cited something that does not support it" call for different fixes. Collapsing them hides which. |
| 3 | Duplicate `claim_id` accepted | Two claims with one id make verification results unattributable. |
| 4 | Decision/claim coherence unenforced | `APPLIES` with no non-missing claim is a conclusion with no reasoning; `INSUFFICIENT_EVIDENCE` with no reason is unauditable. |
| 5 | No mixed-pack fixture | The realistic case: admissible Act section beside withheld Rules. The model must use the Act and say the rule-level evidence is absent — not approximate the rule from the Act. |

## Stop condition (hard)

All five covered by tests, every suite green under `./scripts/run_tests.sh`, and `baseline_eval`
still reports abstention correctness 1.000 with an unsupported-claim rate of 0.

## Unchanged prohibitions

No real LLM call. No PEFT. No Rules-linked benchmark case while the 30 review items are open. No
weakening of the admission gate to make a case pass.

## Monitor

```bash
./scripts/run_tests.sh && python3 scripts/baseline_eval.py
```
