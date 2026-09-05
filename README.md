# placedon-law-backend

Verified legal evidence for **Indian corporate law** — the Companies Act 2013.
Deterministic Python. No language model in any decision path.

> The model may propose. The system must verify. The reviewer decides.

The PoSH Act product this repository began as has been retired; see
`docs/RETIRED_POSH.md`. What remains is the corporate stack.

## What it does today

Given what a company **is** — class, incorporation date, directors, capital,
turnover — it produces a compliance matrix: one row per obligation the Act
imposes, each row saying whether the duty attaches, whether it was met, or
exactly what is missing.

Rows come from the law, not from documents. A company that has uploaded nothing
still gets a full matrix, and the rows with no document behind them are the ones
that matter most.

```bash
python3 scripts/serve_matrix.py        # http://127.0.0.1:8014
```

No API key, no network, no dependencies outside the standard library.

## What it refuses to do

- It never claims an obligation was complied with unless every limb of that
  provision has been decided. Where limbs remain undecided it says so.
- It never serves a statutory threshold it has not properly acquired. The
  small-company test currently **refuses**, naming G.S.R. 700(E) as the missing
  instrument.
- It never repairs a defective government source. Four transcription defects in
  the official text are recorded in `docs/SOURCE_DEFECTS.md` and preserved
  verbatim.
- It makes no accuracy claim. No practising lawyer has reviewed any output, and
  there is no real-document benchmark.

## Layout

```
checker/company_profile.py      company facts; unknown is never zero
checker/classify.py             s.2(85) small-company status, with refusal
checker/prescribed_thresholds.py  dated thresholds, state derived from evidence
checker/obligations.py          the obligation register — matrix rows
checker/matrix_view.py          the HTTP surface, no dependencies
checker/cascade.py              the E3-E6 deterministic verifier
checker/metric_policy.py        the release gate
checker/model_adapter.py        the only place an LLM may be called (stubbed)
corpus/companies_act/           529 sections, hash-stamped
corpus/benchmark/               the frozen benchmark and its governance
docs/                           plans, analyses, source defects, retractions
research/TASKS.md               the open ledger — what is blocked and on whom
```

## Running

```bash
./scripts/run_tests.sh                 # every suite, self-testing, not pytest
python3 scripts/slice_s96.py           # the AGM slice, end to end
python3 scripts/slice_s173.py          # the board-meeting slice
python3 scripts/serve_matrix.py        # the compliance matrix
```

Each module tests itself and prints `[PASS]` / `[FAIL]` and `N/N passed`. There
is no pytest and no third-party test dependency.

## Status

The verification machinery is substantial and the product is small. Read
`docs/FAILURE_MODES.md` before believing anything here works, and
`docs/PLAN_TWO_MONTH.md` for where it goes next.
