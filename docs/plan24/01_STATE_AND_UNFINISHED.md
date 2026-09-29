# 01: Where Themis is, and every piece of unfinished work

## 1. Measured on 2026-09-30, in a fresh cloud clone of `main`

| What | Result | How |
|---|---|---|
| Test gate on `main` | **198 suites, 5 failed, RED** | `./scripts/run_tests.sh` |
| …of which caused by this container | **all 5** (see below) | each failing suite re-run alone |
| Gold set, questions that should be refused | **9 of 14** refused. No rate stated (n < 30); Wilson 95% [0.39, 0.84] | `python3 -m eval.goldset.run` |
| Gold set, questions that should be answered | **no entries** | same |
| Vertical slice (G.S.R. 880(E)) | runs; **4 requirements across 3 task types**. Earlier docs say 5 across 4 | `scripts/themis_slice.py --demo` |
| `/v1/ask` on an IBC-phrased question | `state: partial`, empty pack. It does not say "IBC is not held" | direct call to `checker.api.handle` |
| Routes served by `checker/api.py` | **8**, including `/v1/ask` and `/v1/mca-strip` | the module's own route list |

**The five red suites, and why none is a code regression:**

| Suite | Cause | Kind |
|---|---|---|
| `checker/sarvam_model.py`, `checker/pdf_pages.py` | `pypdf` (dev dependency) absent, then a broken `cffi` | environment; both pass once installed |
| `scripts/review.py` 54/55 | same `pypdf` absence | environment; 55/55 once installed |
| `checker/provenance.py` 113/115 | The "unreadable file" test uses file permissions, and the container runs as root, which can read anything | **the test depends on who runs it** |
| `checker/s96_slice.py` 33/36 | "no copy of Act 1 of 2018 is held": the witness comes from a network cache that a clean clone does not have | **the suite depends on a network cache** |

The last two are real defects of the harness, not of the engine. A gate that passes on one
laptop and fails in a clean clone does not prove what "GREEN" says.

**Not measured here.** The founder's local session reported **229 suites GREEN** on the newest
branch. That figure is recorded as *reported*. This session was not permitted to check that
branch out, so it did not re-run it.

## 2. What exists on the newest branch [R:H]

This is from `git show` on `claude/harvey-india-platform-analysis-d2mmqi`, head `22b8205`.

| Area | Modules (lines) | State in its own words |
|---|---|---|
| Gateway | `gateway/verbs.py` (911), `store.py` (588), `auth.py`, `audit.py`, migrations 001–005 | One verb table generating three surfaces. RLS proved on PostgreSQL 18.6: 53 checks, 0 failures (commit `b0b7a51`) |
| Verbs | `ask`, `review_contract`, `review_document`, `runs.get`, `runs.trace`, `runs.approve`, `runs.reject`, `documents.upload` | from `gateway/verbs.py` |
| Agents | `agents/plans.py` (237), `runtime.py` (290), `review_document.py` (335), `research_question.py`, `review_contract.py` | A run resumes to an identical trace (`bd4eaa2`) |
| Models | `checker/router.py` (781), `azure_model.py`, `public_only.py` (674), `quoted_span.py` (355) | Azure is the only host for matter documents; the free tier sees only published text |
| Contracts | `checker/clauses.py` (324), `checker/playbook.py` (503) | A company standard as data; findings cannot read as legal advice |
| Time | `checker/observation_store.py` (439) | Bitemporal, append-only |
| Orchestration | PLAN_23: 12 layers, steps O1–O9 | Design; O1 partly landed at `22b8205` |

## 3. Every open task, sorted by who can close it

Source: `research/TASKS.md` on the newest branch [R:H]. It has 31 rows marked
open/blocked/ready, plus PLAN_23's O1–O9.

### 3.1 Code can close these now. They are T0

| # | Task | Why it matters to the intelligence layer |
|---|---|---|
| T0.1 | **Land the newest branch on `main`** (a reviewed PR; the founder merges) | Two sources of truth is a failure mode this repo already had, e.g. the two PLAN_16s |
| T0.2 | **Make the harness hermetic.** Replace the permission-based unreadable-file test with an injected `PermissionError`. Commit a fixture of the Act 1 of 2018 witness the s.96 suite needs, as the `.gitignore` already does for other provenance PDFs. Preferably use the Gazette copy; an Indian Kanoon copy is acceptable only under its attribution terms | Every later promotion gate rests on "the gate is green" meaning the same thing everywhere |
| T0.3 | **D-002b:** move `checker/pdf_pages.extract_pages` to `pdfplumber` (already in `requirements-dev.txt`), then re-extract `corpus/rules/board_powers_2014.json` | Unblocks the 30 human-review items. That is the first source of real HUMAN labels |
| T0.4 | **PLAN_23 O1:** finish `review_document`, `runs.approve` and the playbook text, all gated | `runs.approve/reject` is where labels are born (05 §2) |
| T0.5 | **R-013, R-014:** the fetch-policy summary lists its own robots URL; acquisition logs live in two places | Small; they sit on the acquisition path T3 depends on |
| T0.6 | **Website drift.** `placedon-claude-legal-3300/AGENTS.md` says the backend has "exactly six routes" and that `/v1/ask` does not exist. `main` serves eight, including `/v1/ask` | A contract the frontend builds against has to be true |
| T0.7 | **A-011:** independently re-verify `/v1/ask` (status "fixed — awaiting re-verification") | It is the answer path every new intent reuses |

### 3.2 A founder or counsel decision closes these

| Task | Decision needed | This plan's recommendation |
|---|---|---|
| **G0.5** | Evidence order: is UNFETCHED_CORROBORATION stronger than INFERRED? | Decide it. It gates the ontology (T1), because every property carries an evidence state |
| **G0.3** (blocked) | The scope lexicon needs provision-level text of 7 unheld Acts | **Acquire those Acts as DECLARED reference text, not held law.** Take the Gazette PDF of each Act (eGazette: permitted by browser download). Use it only to cite lexicon terms. Register no obligation from it. That keeps the tested invariant ("no obligation for a body not held") intact. **[I]**, legal-verifier to confirm |
| **R-012** | India Code robots returns 5xx, so the fetcher fails closed | Keep failing closed. Acquire by human browser download with a recorded URL and date (the S-002 precedent) |
| **R-015** | The audit hash chain is unanchored | Anchor the chain head daily to a place the operator cannot rewrite: a signed git tag, or a per-tenant emailed digest. Architect decides |
| L-007, A-002, A-003–A-010 | As recorded in the ledger | Unchanged by this plan |
| Judge-level analytics | Lawful in India? (04 §6) | **Counsel, before any design work** |
| CC-BY on court text | Is the maintainer's CC-BY grant valid for judgments? (PLAN_19 02 §5) | **Counsel, before T5** |

### 3.3 A person closes these. No code substitutes

| Task | Why it is the critical path |
|---|---|
| **H-001:** one practising Company Secretary reviews real output | Open 26 days. Every accuracy statement, every promotion gate and every per-tenant model in this plan needs HUMAN labels, and this is where the first ones come from |
| **B-001 / B-002:** a benchmark of 30–50 documents including *defective* ones; accessible testers | R-008: scanner false negatives have never been measured, because every corpus document is compliant |
| H-002, H-004 | Indian Kanoon tier, Reddit OAuth, both founder-owned |

### 3.4 Research rows, unchanged

R-004 (non-circular reconstruction benchmark), R-007, R-009, R-011: still open, not on T0's path.

## 4. The order, and why

```
T0.2 hermetic harness ─┐
T0.1 land branch ──────┼─► T0.3 D-002b ─► 30 review items reviewable ─► H-001 session ─► first HUMAN labels
T0.4 O1 finish ────────┘                                                       │
                                                                               ▼
                                                   T2 learning loop has something to learn from
```

**Why labels come before intelligence.** The whole learning plane (05) is a function of human
decisions, and there are zero today. A self-improving system with n = 0 labels has nothing to
improve on. It can only drift.
