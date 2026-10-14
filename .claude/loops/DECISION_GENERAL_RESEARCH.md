# DECISION — General-purpose research (find a case / case studies by generic query)

- **Status:** PROPOSED (design-first, before any code)
- **Date:** 2026-10-14
- **Branch:** `claude/general-research` (cut from `main` @ 82b70d1)

## The ask

A user writes generically — *"the Tata Sons vs Cyrus Mistry battle, I need the documents"*,
*"a 2026 data-protection case"*, *"case studies on oppression"* — and expects results. Today
`ask` and `research.multi` search **only** the held Companies Act 2013 corpus, so a case query
correctly abstains (*"nothing on point was found"*). The product should also **find case law**
when asked generically — as supporting authority, never as a verified statutory answer.

## What already exists (reuse, do not rebuild)

- **`checker/sources/judgments_open.py` (`OpenJudgments`)** — a keyless, anonymous-HTTPS reader
  for the AWS Open Data judgment datasets `indian-supreme-court-judgments` and
  `indian-high-court-judgments` (ap-south-1, CC-BY-4.0, Dattam Labs, owner-approved 2026-10-05,
  terms recorded in `checker/sources/terms.py`). It byte-asserts `%PDF`, fails closed, and is
  tier **LICENSED** — `tiers.can_verify(LICENSED)` is False, so a judgment may SUPPORT an answer
  and can never make one VERIFIED. Transport and the metadata reader are INJECTED (the gate uses
  fixtures and opens no socket; `--live` uses the real ones).
- **Source model** — `checker/source_picker.py` + `checker/sources/tiers.py`: HELD (verify) /
  LICENSED (support) / PUBLIC. `aws_sc_judgments` + `aws_hc_judgments` are LICENSED with
  `may_fetch: true`.
- **`sources.search` verb** — exists, but its search loop only iterates `HeldCorpus` +
  `ClientDocuments`; it never calls `OpenJudgments`.

## The gaps

1. `sources.search` does not search the judgment datasets (the connector is never invoked).
2. No **routing**: nothing decides "this is a case query → search judgments" vs "statute query → ask".
3. **Discovery**: the datasets are PDFs + a metadata parquet (HC partitioned by court + bench).
   There is no full-text index, so "find a Tata case" must match on METADATA (parties, title,
   year, court) — which needs a parquet reader (`pandas` + `pyarrow`), a heavy dependency the
   connector already assumes.
4. **Frontend**: no surface for case search; results must render as LICENSED *supporting
   authority* (never VERIFIED), visibly distinct from a statute answer.

## Decisions (flagged — these have real trade-offs)

- **D1 — dependency.** Reading the metadata parquet needs `pandas` + `pyarrow` (heavy; CLAUDE.md
  requires a stated reason for any new dependency). **RECOMMENDED:** build a **slim metadata
  index offline** (one-off script extracts parties/title/date/court/S3-key into a compact in-repo
  file), so the *runtime* carries no pandas; only the offline index-builder does. Falls back to
  gating pandas behind `--live` if an offline index proves infeasible.
- **D2 — search quality.** v1 matches on **metadata** (party name, year, court), not full text:
  "Tata Sons" matches by party; "2026 data case" by year + title keyword. Full-text over judgment
  bodies is out of scope v1 (no index; too large). State this limit on screen.
- **D3 — tier discipline (non-negotiable).** Case results are **LICENSED**: they support, never
  verify. The UI shows "supporting authority — not a verified statutory answer." The scope.py
  invariant stands: **no obligation may exist for a body not held** — case search returns
  authorities, never obligations or findings.
- **D4 — routing.** A conservative classifier: default to the statute (`ask`/HELD); offer/route to
  case search when the statute abstains OR the query names parties / a case / a court. Explicit,
  never silent.
- **D5 — where it runs.** Judgment reads are live S3 GETs (keyless, ap-south-1). Fine on the
  hosted gateway; the gate stays fixture-only (no network), per the connector's injected transport.

## Plan (loop iterations, each gate-GREEN, failing test first, one change per commit)

1. **Offline metadata index** — a script that reads the datasets' metadata once (pandas, offline)
   into a compact in-repo index (parties, title, date, court, S3 key). Fixtures for the gate.
2. **Wire discovery into `sources.search`** — search the index for LICENSED judgment hits by
   party/year/court; return `Evidence(LICENSED)` with the S3 key; `OpenJudgments.fetch/quote`
   serves the verbatim passage on demand.
3. **Routing verb** — a `research.cases` verb (or extend `sources.search`) + the D4 classifier;
   `roles.REQUIRED` entry; MCP per policy; CLI/REST parity test holds.
4. **Frontend** — a "Case law" surface (or Ask routes case queries to it) rendering LICENSED
   authorities distinctly (support, not verified), citations re-read on open. Tests + screenshots.
5. **Integrate** — verify "Tata Sons Cyrus Mistry" and "a 2026 …" return supporting judgments,
   end to end.

## Reversal condition

If judgment discovery cannot be made reliable from metadata, or the dependency cost is
unacceptable and no slim index suffices, **STOP and ship nothing**: keep case search out, and let
`ask` keep its honest behaviour (naming the judgments source as *available but not searched*).
Nothing in the statute/audit path depends on this — it is purely additive and removable.

## Companion — login

The deployed `/login` works (passcode, verified repeatedly). The real "login fix" is shipping
**personal accounts** (email/password): backend `auth.login` — see `[[DECISION_ACCOUNTS]]`,
STEP 0 ready on `claude/accounts` — plus the already-built frontend (PR #22), then deploy with
`APP_AUTH_MODE=accounts`. That is a separate, scoped build, not a bug in the login page.
