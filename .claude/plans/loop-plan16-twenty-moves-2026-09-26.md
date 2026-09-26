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
| 1 | BUD-1 | `budget.py`: distinguish the spend-cap 429 (`enforced_spend_limit_reached`, no `retry-after`) from a rate-limit 429. Retrying the former fails for the rest of the month. | — | **running** | a2ad2c389a8b5bb9d | | |
| 2 | BUD-2 | `cost_inr()` takes **four** counters: `input`, `cache_creation`, `cache_read`, `output`. `input_tokens` counts only tokens after the last cache breakpoint — treating it as total under-bills by up to 90%. | BUD-1 | **running** | a2ad2c389a8b5bb9d | | |
| 3 | BUD-3 | Tokens-per-page **per model**. Claude 4.7+ produces ~30% more tokens for identical text, so `PRICING` alone is half a cost model. | BUD-2 | **running** | a2ad2c389a8b5bb9d | | |
| 4 | BUD-4 | `Store` Protocol gains `reserve`/`settle`. Reserve the worst case (`count_tokens` + `max_tokens`); settle to actual. A guard that only records after the fact cannot refuse. | BUD-3 | **running** | a2ad2c389a8b5bb9d | | |
| 5 | FETCH-1 | Generalise `04664f5`: every fetcher asserts Content-Type and magic bytes, not status alone. `checker/robots.py`, `commencement.py`, `revocation.py`, the watchers. | — | **running** | ac3998707ad496e80 | | |
| 6 | FETCH-2 | `provenance.py`: re-admit `www.indiacode.nic.in` (it serves the real PDFs) **with** the FETCH-1 content check, and record why the earlier exclusion was wrong. | FETCH-1 | ready | | | |
| 7 | PIT-1 | `applicable(company_facts, obligation, as_at_date) -> decision + instrument version relied on`. Never a boolean stored against a company. "Is this a small company?" has had five answers. | — | ready | | | |
| 8 | PIT-2 | Threshold history as data: s.2(85) (13-02-2015, 09-02-2018, 01-04-2021, 15-09-2022, 01-12-2025), s.135 (19-09-2018), s.177 (07-05-2018), s.204 (01-04-2020). Each with its instrument. | PIT-1 | ready | | | |
| 9 | PIT-3 | The in-force-at-date lookup must reach **circulars**, not only Acts and Rules. SEBI reg. 27(2)(a) has no timeline in the regulation; the 30-day figure lives in a Dec-2024 circular. | PIT-1 | ready | | | |
| 10 | AGM-1 | Store `agm_actual` and `agm_due` separately; derive MGT-7 (60d), AOC-4 (30d), ADT-1 (15d) from the pivot. Handle the Registrar's 3-month extension (not for a first AGM) and the OPC carve-out (AOC-4 at 180d, no AGM). | PIT-1 | ready | | | |
| 11 | KYC-1 | The DIR-3 KYC row — **the demo**. Triennial since G.S.R. 943(E) w.e.f. 31-03-2026; next due 30-06-2028. Every pre-2026 calendar says "30 September, annually" and is wrong. **Pull the gazette first**; the finding is secondary-sourced and must not enter the register on a blog post. | PIT-2 | ready | | | |
| 12 | PROV-1 | Every retrieved chunk carries `(instrument, section, version, in_force_from, in_force_to)`. Precondition for a safe answer cache; this is retrieval work, not cache work. | — | ready | | | |
| 13 | BITEMP-1 | Bitemporal statutory facts: `valid_time` (rewritten by a retrospective amendment, including into the past) and `transaction_time` (append-only). Without the second axis we cannot distinguish "we were wrong" from "the law changed" — the entire liability position. | PROV-1 | **complete — built by the other session**, not by this loop | Themis session | | `090efb8` `990bd09` |
| 14 | CACHE-1 | Answer cache keyed on `H(document)·H(question)·prompt_version·model+params·H(law_state_vector)`, where the vector is the provenance **actually used**. A hit whose versions have moved is a miss **plus an alert**. | BITEMP-1 | ready | | | |
| 15 | CACHE-2 | Reverse index `(instrument, section, version) -> answer_ids`, so "which tenants received which answers relying on s.X between A and B" is answerable. Invalidation is a notification workflow, not a `DEL`. | CACHE-1 | ready | | | |
| 16 | RAG-1 | Order retrieved chunks by **position in the source document**, not relevance. OP-RAG: 16K retrieved scored F1 44.43 against 34.32 for a full 128K context. Free accuracy. | PROV-1 | ready | | | |
| 17 | RAG-2 | Self-Route: one cheap call decides "can I answer from these chunks?", escalating only on no. Maps onto the existing `normal · budget · offline` ladder. (M) | RAG-1 | ready | | | |
| 18 | ASK-V | Re-verify `/v1/ask`. Its three blocking defects were fixed 19-09 and it has sat "awaiting independent verification" since; nothing may wire a client until that passes. | — | ready | | | |
| 19 | MCP-1 | MCP server gains OAuth 2.1 + PKCE (S256) and a remote transport, making it BYOMCP-pluggable into Harvey. Thirteen read-only tools, no write of any kind — which is the safe thing to hand an agent. | — | ready | | | |
| 20 | D4-2 | Wire the lawyer summary into the server and page. **BLOCKED** on Anthropic credit — no Opus call has ever run through the tracer, and its thresholds are unvalidated against real prose. Do not wire an unproven live call. (M) | credit | blocked | | | |

## Log
- 26-09 04:30 opened. Predecessor loop complete and reported in `docs/NEXT10_REPORT_2026_09_17.md`.
- 26-09 04:40 **loop started, founder asleep.** Two implementers on disjoint paths: **BUD-1…4**
  (`a2ad2c389a8b5bb9d`, `backend/budget.py` only) and **FETCH-1** (`ac3998707ad496e80`, the fetchers).
  Both told: tests RED first, no network in tests, no `git add -A`, no push, and hand back rather
  than block silently past ~10 minutes.
- 26-09 04:45 **filename collision with the other session, handled without touching their work.**
  I created this runbook as `loop-twenty-moves-2026-09-26.md` and committed it (`da042d9`); the
  Themis session then wrote its own PLAN_19 G0–G7 runbook over that exact path in the working tree.
  Their content is uncommitted and **was left exactly as found** — overwriting it would be the same
  class of harm as the `git add -A` incident of 25-09, from the other direction. This loop's runbook
  is therefore restored from `da042d9` to **`loop-plan16-twenty-moves-2026-09-26.md`**, and the
  original path belongs to them. Both running agents were told the path moved.
  Worth recording as a hazard in its own right: two sessions independently chose the same obvious
  filename on the same day. Plan files should carry the plan they serve in the name, which is why
  this one now says `plan16`.
- 26-09 14:50 both implementers resumed past the 13:30 reset. **BUD-1 committed** (`66c9a5c`, the
  spend-cap 429 distinction). Note `backend/budget.py` is clean in the working tree, so BUD-2 and
  BUD-3 live only in that agent's scratch copy — it was told to check the scratch survived before
  assuming it did. FETCH-1 has five dirty files and is verifying a claim one of its own comments
  makes rather than asserting it, which is the right instinct and is exactly how the `assistant.css`
  overflow comment and the `CLAUDE.md` dead-host claim went wrong.
- 26-09 14:52 **move 13 (BITEMP-1) is already built, by the other session, and better motivated than
  my runbook entry.** `checker/observation_store.py` (`090efb8`) is an append-only bitemporal store
  for `ontology.Observed` whose stated purpose is *"What did Themis tell this client on 31 March, and
  on what basis?"* — answerable years later because a correction is a NEW observation with a later
  `known_at`, never an edit. `990bd09` then makes `event_log` distinguish a **recorded** transaction
  time from a **defaulted** one, on the reasoning that a defaulted `known_at` which looks recorded is
  the silent-default failure.
  Their no-index decision is derived from a red-team finding of theirs (RT-11): `operation_store.save`
  wrote whole-object snapshots, so two callers who each closed a different requirement produced a file
  holding only the second one's work. An append-only log cannot lose a row that way — but an index is
  a mutable whole-file structure, so rebuilding it after two concurrent appends is RT-11 one layer
  down. That is a better argument than anything in my row 13.
  **Consequences for this loop:** row 13 is complete and credited to them. **Rows 14 and 15 (the answer
  cache and its reverse index) must build on `observation_store.py`, not a second store beside it** —
  two append-only ledgers in one repo is how they drift, which is the same warning I had just given
  BUD about its `reserve`/`settle` persistence. I came within one launch of shipping the duplicate I
  was warning about, and only checking the commits stopped it.
