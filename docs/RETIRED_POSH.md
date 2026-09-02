# The PoSH product, retired

Closed `R-010`. This repository began as a PoSH Act compliance checker for
Indian SMEs and pivoted to Indian corporate law. The PoSH surface stayed
deployed and tested long after the pivot, which meant the only live HTTP
endpoints belonged to the abandoned product while the corporate work was
reachable only from a Python prompt.

## What was removed, and why it was safe

31 files, roughly 8,500 lines. Nothing removed was in `scripts/run_tests.sh`,
and the suite was green before and after every step.

**The surface.** `checker/app.py` (825 lines of FastAPI routes), `api/index.py`
(the Vercel entry point), `vercel.json` (the deployment that served it), and
`scripts/verify.py` — the 39-check verification ratchet, which its own docstring
ties to `checker/app.py`'s stylesheet.

**The modules it carried.** `assess.py`, `rules.py`, `documents.py`,
`register.py`, `ratelimit.py`, `retrieval.py`, `ic_order.py`, `board_report.py`,
`distress.py`, and `scripts/review_pack.py`. Each was orphaned the moment
`app.py` went, or read the PoSH corpus directly.

**A closed cluster.** `ask_engine.py`, `test_unlock.py`, `path_validity.py`,
`epistemic_status.py`, `provision_graph.py` and `verifier.py` referenced only
each other and the PoSH corpus. `ask_engine` broke outright when `retrieval`
went. None was in the suite.

**The corpus and its ingestion.** `corpus/provisions/posh_act_2013.json` (30
sections), `posh_rules_2013.json`, `scripts/ingest_posh.py`,
`scripts/ingest_posh_rules.py`, and five `scripts/bench_*.py` benchmarks plus
`scripts/exercise_llm.py`.

## What was deliberately kept

`checker/text_search.py` mentions PoSH only in a docstring describing the move,
and is in the suite. `scripts/split_subsections.py` and
`scripts/check_transcription.py` name PoSH in prose but are generic ingestion
tools that the Companies Act corpus can use.

## What this costs

`provision_graph.py` is gone, and `FEATURE_PLAN_INDIA.md` proposed sourcing a
matrix column's `depends_on` from it. That module was bound to the PoSH corpus
at module level, so it could not have served the Companies Act without being
rewritten. A corporate provision graph is a new piece of work, not a salvage.

The Vercel deployment is now unconfigured. That is intended: it served the
abandoned product, and the corporate surface is deliberately local-only until
serving company financials over the network has had its own security work.
