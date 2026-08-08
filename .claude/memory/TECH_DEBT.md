# Tech debt

Shortcuts taken knowingly, with the condition that would make each worth paying off. Debt that is
merely *suspected* belongs in `BACKLOG.md`; this file is only for things chosen on purpose.

| # | Shortcut | Why it was right | Pay it off when |
|---|---|---|---|
| T-1 | No vector search — keyword route + term-overlap scan | 30 sections. Torch is ~2GB to beat a sub-millisecond scan | The corpus reaches the labour codes (~500 sections) |
| T-2 | Agent index is BM25F, not embeddings | 6,000 lines, 0.05 ms mean, exact recall. See `scripts/index_codebase.py` | Same trigger as T-1, or when prose search starts missing |
| T-3 | No PDF library — print-ready HTML + browser print | weasyprint needs cairo/pango and does not run on Vercel serverless | A server-side PDF is genuinely required (bulk generation) |
| T-4 | Corpus is JSON on disk, not Postgres | One instrument, 30 provisions, sha256-pinned, no network dependency | A second instrument, or multi-writer access |
| T-5 | Tests inside modules, no pytest | One file to open; `verify.py` aggregates | A contributor who is not the founder |
| T-6 | MCA provisions from a secondary reproduction | The rule matters now; recording it with the weakness stated beats holding it in someone's head | BACKLOG M-4 — ingest the Gazette |
| T-7 | Report passed to `/result` in the query string | 2,786 chars today; works | ~10 findings, where some browsers truncate the URL |
| T-8 | No git remote | Everything is on one laptop | **Now.** This is not a shortcut, it is an unbacked-up asset |

**T-8 is the one to fix today.** Every other row has a real trigger. That one just has a
disk that has not failed yet — and on 8 Aug an `ln -sf` destroyed four command files that were
recoverable *only* because they had been committed. Git was the whole recovery path, and it is
currently one laptop deep. See LESSONS L-10.
