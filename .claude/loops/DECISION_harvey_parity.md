# Decision: Harvey-style features, trust-first

2026-09-30 · /loop phase D · reads `RESEARCH_harvey_parity.md`

## Selected: Option B — the trust-first sequence H0 → H6

## Rejected, with reasons

**A (parity sprint).** Rejected: the gold set refuses rightly on 5 of 17 dev rows. Adding web
search, judgments and client repositories in parallel multiplies the inputs a failing gate lets
through, and would add several paid dependencies at once, each of which needs escalation.

**C (integrate only).** Rejected as the plan, kept as a channel: the hosted MCP route (PLAN_22 D7)
stays, but on its own it gives the in-house buyer no workspace, no drafts and no review tables.

## The sequence

Each step ships alone, behind its own tests, and the next does not start until the previous one's
check is green.

| Step | What | Files (new unless marked) | Tests written before the code |
|---|---|---|---|
| **H0** Refusal gate | Make every refusal row in the gold set dev split refuse, with no loss on answer rows; then run the held-out split **once** and report it | `checker/ask_scope.py` (edit), `checker/ask.py` (edit), `eval/goldset/` (no label edits) | The 12 failing refusal rows as module tests; the 13 answer rows must not regress; an off-topic question never returns retrieved provisions |
| **H1** Source framework | One interface for every source, each result carrying a **tier**: HELD (our corpus), OFFICIAL_LIVE (a host in `OFFICIAL_SOURCE_HOSTS`, fetched now), LICENSED (Indian Kanoon), CLIENT (the tenant's own documents), WEB. Only HELD can make a legal claim VERIFIED. Verbs `sources.list`, `sources.search` (read-only, so also MCP) | `checker/sources/__init__.py`, `checker/sources/tiers.py`, `checker/sources/held.py`, `checker/sources/client.py`, `gateway/verbs.py` (edit) | A WEB or LICENSED result can never produce VERIFIED; every source passes `robots.py`; every result has URL or document id, fetch time and sha256 |
| **H1b** Connectors | Indian Kanoon API (judgments; attribution; prepaid), MCA company master data from the OGD platform (company facts), BSE/NSE announcements (listed-company disclosures). Each needs its terms read and recorded first | `checker/sources/indiankanoon.py`, `checker/sources/mca_ogd.py`, `checker/sources/exchange.py` | Terms file present or the connector refuses to load; a 200 with HTML where JSON/PDF was expected is an error, never an empty result |
| **H2** Web research | A plan step that fans out search queries through the queue, fetches pages (robots enforced), stores them hashed, and admits a sentence only with a quoted span. Injected instructions are flagged, never stripped. Web evidence supports facts only | `checker/sources/web.py`, `agents/web_research.py` | A page containing "ignore previous instructions" is flagged and its text kept verbatim; a web-only claim of law is refused; every admitted sentence has a span that byte-matches the stored page |
| **H3** Drafts with versions | Free-form drafts (client email, memo) on `provenance_slots`: statements of law bind to verified claims and carry citations; other sentences are MODEL_SUGGESTION and marked. Every save is a version; diff between any two; edit by hand or "revise"; export .docx | `checker/drafts.py`, `gateway/migrations/007_drafts.sql` (tenant-scoped, FORCE RLS), `gateway/verbs.py` (edit) | Approval blocked while any MODEL_SUGGESTION is unaccepted; a diff of two versions is exact; RLS: tenant A cannot read tenant B's drafts (run `scripts/rls_integration.py`) |
| **H4** Review tables | Pick documents, define columns (text, date, amount, yes/no, clause); each cell is a job on the queue; each answer is FOUND with a quote, NOT_FOUND stated explicitly, or NEEDS_LAWYER. Export CSV | `checker/review_table.py`, `gateway/migrations/008_review_tables.sql`, `agents/review_table.py` | A FOUND cell without a byte-matching quote is rejected; per-column precision and recall on CUAD with Wilson intervals, including the false "not found" rate; no accuracy claim without human labels |
| **H5** Word add-in | Side panel in Word: run a playbook on the open document, insert suggestions as tracked changes computed by our own diff, comments carry citations | frontend repo: `word-addin/` | Suggestion applied as a tracked change, never a silent overwrite; transport error shown as error |
| **H6** Workflows library | Saved compositions of fixed intents + playbook + template. Not free-form agents | `agents/workflows.py` | A workflow can only reference registered intents and capabilities |

## Escalate, do not decide

- Every new paid dependency: Indian Kanoon API credit, a web search API, Microsoft 365 developer
  tenant. Each goes to the user with its price and terms before code depends on it.
- Migrations 007 and 008 (schema changes).
- `python-docx` for .docx export — a new dependency; reason: .docx is the format lawyers exchange.
- Any statement a draft makes about law.

## Rollback

Each step is its own commits and its own verbs. Rolling back a step removes its verbs from the
table; no step changes an existing verb's behaviour except H0, which is reverted by its commit.

## Reversal conditions

- If H0 cannot bring the dev refusal rows to 17/17 without losing answer rows, **stop widening**:
  no H1b/H2 until it does.
- If the first lawyer sessions value review tables over drafts, swap H3 and H4.
- If Indian Kanoon's terms forbid storing the text we would quote, H1b uses it for discovery only
  and quotes nothing from it.

## Not mirrored into DECISIONS.md

A second session is building on this branch. Editing a shared file from here risks a conflict;
the laptop session mirrors this decision when it starts H0.
