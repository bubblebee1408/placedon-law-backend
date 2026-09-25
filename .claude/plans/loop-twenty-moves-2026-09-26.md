# Twenty moves — the PLAN 16 build, run as a loop

Opened 26-09-2026 ~04:30, founder asleep. Supersedes `loop-next10-2026-09-17.md`, which is complete.
Source of truth for WHAT: `docs/PLAN_16_BACKEND_ARCHITECTURE.md` (Parts I–III).

## Iteration protocol
1. Read this file; `git log --oneline -5`; `git status --short`.
2. If a job is `running`, wait — schedule a fallback wakeup. Completions arrive as notifications.
3. Otherwise take the first `ready` row whose dependencies are `complete`. Launch its **implementer**
   (background Agent). Record the agent id. Status → `running`.
4. Implementer returns → Status `verifying`; launch an independent **verifier** (fresh context,
   read-only). Record its id.
5. Verifier returns → **check 3** in the main session: read the diff, re-run the gate, hand-check two
   claims, then push. PASS → `complete`. FAIL → send findings back, `fixing`. Two behavioural FAILs
   → `blocked`, reason recorded.
6. Never two code jobs on overlapping paths. Read-only jobs may run beside one code job.
7. If an agent dies (spend/session/weekly limit, watchdog, network): check `git log`, `git status`
   and the files it names BEFORE relaunching; resume with SendMessage, never a fresh agent.
8. **Long commands belong to the main session**, in a `run_in_background` Bash job. An agent that
   blocks silently gets killed by the 600 s watchdog — this cost the last loop several hours.
9. When every row is `complete` or `blocked`: write `docs/TWENTY_MOVES_REPORT_2026_09_26.md`,
   commit, push, PushNotification, stop.

## Checked three times (the founder's rule)
- **1 implementer**: test first, seen failing (RED), then passing; full gate GREEN; commit. No push.
- **2 verifier**: different agent, no stake. Reads the diff, re-runs the gate, makes ≥3 concrete
  attempts to break the claim. PASS/FAIL with evidence. Never edits, never commits.
- **3 main session**: reads the diff, re-runs the gate, hand-checks two claims, then pushes.

**Doubt every result, including a verifier's.** This loop's predecessor had three verifier findings
that were themselves wrong, and one research claim ("a CIN has a check digit") that was false and
would have shipped. A confident report is the kind that gets believed without checking.

## Shared-repo rules (another Claude session commits to this branch)
`git status --short` before every commit · stage paths explicitly, **never `git add -A`** (a sibling
session swept an agent's work-in-progress into an unrelated commit on 25-09) · retry on "cannot lock
ref HEAD" · never revert/rebase/amend another session's commit · watch for a staged deletion of a
file that still exists.

## Stop rules
Never edit `~/PlacedOn/Placedon-law-business-plan` (PUBLIC) · never deploy · **never push the
frontend repo** (a branch push triggers a Vercel preview) · no captcha/WAF bypass · downloads only
from official hosts · **never run a record-writing command against a live record** — copy it to a
scratch dir first; re-running a seeder that rebuilds records from scratch is how a review queue gets
wiped · **never self-attest a human check** · preserve uncertainty, never repair a source · one
logical change per commit.

**Spend:** model calls allowed for moves marked (M). Public documents only. Keys from `.env`, never
printed. The Anthropic account had **no credit** at 25-09 — any move needing a live Opus call is
`blocked` until the founder tops up, and must say so rather than faking a result.

## The moves

| # | ID | Move | Depends | Status | Impl | Ver | Commits |
|---|---|---|---|---|---|---|---|
| 1 | BUD-1 | `budget.py`: distinguish the spend-cap 429 (`enforced_spend_limit_reached`, no `retry-after`) from a rate-limit 429. Retrying the former fails for the rest of the month. | — | ready | | | |
| 2 | BUD-2 | `cost_inr()` takes **four** counters: `input`, `cache_creation`, `cache_read`, `output`. `input_tokens` counts only tokens after the last cache breakpoint — treating it as total under-bills by up to 90%. | BUD-1 | ready | | | |
| 3 | BUD-3 | Tokens-per-page **per model**. Claude 4.7+ produces ~30% more tokens for identical text, so `PRICING` alone is half a cost model. | BUD-2 | ready | | | |
| 4 | BUD-4 | `Store` Protocol gains `reserve`/`settle`. Reserve the worst case (`count_tokens` + `max_tokens`); settle to actual. A guard that only records after the fact cannot refuse. | BUD-3 | ready | | | |
| 5 | FETCH-1 | Generalise `04664f5`: every fetcher asserts Content-Type and magic bytes, not status alone. `checker/robots.py`, `commencement.py`, `revocation.py`, the watchers. | — | ready | | | |
| 6 | FETCH-2 | `provenance.py`: re-admit `www.indiacode.nic.in` (it serves the real PDFs) **with** the FETCH-1 content check, and record why the earlier exclusion was wrong. | FETCH-1 | ready | | | |
| 7 | PIT-1 | `applicable(company_facts, obligation, as_at_date) -> decision + instrument version relied on`. Never a boolean stored against a company. "Is this a small company?" has had five answers. | — | ready | | | |
| 8 | PIT-2 | Threshold history as data: s.2(85) (13-02-2015, 09-02-2018, 01-04-2021, 15-09-2022, 01-12-2025), s.135 (19-09-2018), s.177 (07-05-2018), s.204 (01-04-2020). Each with its instrument. | PIT-1 | ready | | | |
| 9 | PIT-3 | The in-force-at-date lookup must reach **circulars**, not only Acts and Rules. SEBI reg. 27(2)(a) has no timeline in the regulation; the 30-day figure lives in a Dec-2024 circular. | PIT-1 | ready | | | |
| 10 | AGM-1 | Store `agm_actual` and `agm_due` separately; derive MGT-7 (60d), AOC-4 (30d), ADT-1 (15d) from the pivot. Handle the Registrar's 3-month extension (not for a first AGM) and the OPC carve-out (AOC-4 at 180d, no AGM). | PIT-1 | ready | | | |
| 11 | KYC-1 | The DIR-3 KYC row — **the demo**. Triennial since G.S.R. 943(E) w.e.f. 31-03-2026; next due 30-06-2028. Every pre-2026 calendar says "30 September, annually" and is wrong. **Pull the gazette first**; the finding is secondary-sourced and must not enter the register on a blog post. | PIT-2 | ready | | | |
| 12 | PROV-1 | Every retrieved chunk carries `(instrument, section, version, in_force_from, in_force_to)`. Precondition for a safe answer cache; this is retrieval work, not cache work. | — | ready | | | |
| 13 | BITEMP-1 | Bitemporal statutory facts: `valid_time` (rewritten by a retrospective amendment, including into the past) and `transaction_time` (append-only). Without the second axis we cannot distinguish "we were wrong" from "the law changed" — the entire liability position. | PROV-1 | ready | | | |
| 14 | CACHE-1 | Answer cache keyed on `H(document)·H(question)·prompt_version·model+params·H(law_state_vector)`, where the vector is the provenance **actually used**. A hit whose versions have moved is a miss **plus an alert**. | BITEMP-1 | ready | | | |
| 15 | CACHE-2 | Reverse index `(instrument, section, version) -> answer_ids`, so "which tenants received which answers relying on s.X between A and B" is answerable. Invalidation is a notification workflow, not a `DEL`. | CACHE-1 | ready | | | |
| 16 | RAG-1 | Order retrieved chunks by **position in the source document**, not relevance. OP-RAG: 16K retrieved scored F1 44.43 against 34.32 for a full 128K context. Free accuracy. | PROV-1 | ready | | | |
| 17 | RAG-2 | Self-Route: one cheap call decides "can I answer from these chunks?", escalating only on no. Maps onto the existing `normal · budget · offline` ladder. (M) | RAG-1 | ready | | | |
| 18 | ASK-V | Re-verify `/v1/ask`. Its three blocking defects were fixed 19-09 and it has sat "awaiting independent verification" since; nothing may wire a client until that passes. | — | ready | | | |
| 19 | MCP-1 | MCP server gains OAuth 2.1 + PKCE (S256) and a remote transport, making it BYOMCP-pluggable into Harvey. Thirteen read-only tools, no write of any kind — which is the safe thing to hand an agent. | — | ready | | | |
| 20 | D4-2 | Wire the lawyer summary into the server and page. **BLOCKED** on Anthropic credit — no Opus call has ever run through the tracer, and its thresholds are unvalidated against real prose. Do not wire an unproven live call. (M) | credit | blocked | | | |

## Log
- 26-09 04:30 opened. Predecessor loop complete and reported in `docs/NEXT10_REPORT_2026_09_17.md`.
