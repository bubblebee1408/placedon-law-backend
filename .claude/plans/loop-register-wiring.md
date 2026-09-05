# Loop runbook — register wiring

Started 2026-09-05. Pattern: **sequential**, mode **safe**.

## Isolation (why this branch exists)

A peer Claude session (`nishantsingh-32`, interactive) is committing to
`engine/entailment` in `~/PlacedOn/placedon-law-backend` continuously — it landed
`e5d0181`, `2ad774a` and `1a455f0` during loop setup alone. Two autonomous writers
on one ref would race, and switching branches in the shared checkout would yank the
working tree out from under a live session.

So this loop runs in a **separate worktree on its own branch**:

    worktree   ~/.worktrees/placedon-loop
    branch     loop/register-wiring   (forked from engine/entailment @ 1a455f0)

The operator merges when they have read the diff. The loop never pushes to
`engine/entailment` and never touches the main checkout.

## The one rule this loop must never break

**Do not perform a human-gated step.** Carried over from
`docs/NEXT_MOVE_PLAN_2026_09_04.md`:
- **H-B** — a lawyer resolves the `NEEDS_LAWYER` labels in `retrieval_eval.py`.
- **H-C** — a practising CS reviews the evidence pack (validation kit).

Neither may be faked or decided by the loop. They are the operator's.

## Queue verification (done before writing this file)

The documented T1–T6 queue is complete, and two of three candidate tasks turned
out to be already done — checked, not assumed:

| Candidate | Status | Evidence |
|---|---|---|
| Wire s.185/186/188 into the register | **ALREADY DONE** | `CA13-S185-LOANS-DIRECTORS`, `CA13-S186-LOAN-INVESTMENT`, `CA13-S188-RPT` are live rows in `obligations.py` |
| CIN/DIN as identity in `entity_graph` | **DROPPED** | peer session shipped `checker/mca_aggregator.py` (`1a455f0`) mapping CIN into the graph; and `entity_graph.py` deliberately excludes DINs as PII, so "DIN as identity" contradicts a standing design decision |
| s.180 / s.184 register rows | **OPEN** | both deciders exist (`checker/s180.py`, `checker/s184.py`) but `grep -c 's180\|s184' obligations.py` = 0 |

## The autonomous queue

- [x] **A1 — s.180 and s.184 as company-level register rows.**
  Both are transaction-scoped deciders with no row in the obligation register, so
  a company with no documents is never told these controls exist. Mirror the
  established `decided_by=` pattern used for s.185/186/188.
  - `Evidence.borrowings_s180: tuple | None` (tuple[s180.BorrowingFacts])
  - `Evidence.director_contracts_s184: tuple | None` (tuple[(director, counterparty)])
  - `_decide_s180` — refuse on None; EXCEEDS_NEEDS_SPECIAL_RESOLUTION ⇒ undetermined
    (the resolution's passing is not established), never a false "satisfied".
  - `_decide_s184` — refuse on None or a missing entity graph; INTERESTED_MUST_DISCLOSE
    ⇒ undetermined (whether disclosure was actually made is not established).
  - `limbs_not_decided` must carry s.180's unmodelled (a)/(b)/(d) limbs.
  - Acceptance: register goes 13 → 15 rows; a profile with no evidence yields both
    rows as APPLIES_UNDETERMINED naming what would settle them; full runner green.

- [x] **A2 — widen `cross_section_eval`.** Was blocked on an account session limit,
  now clear. Labels are read off section titles and need no legal judgement. Add
  cases and re-measure p@1 / recall@5 against the frozen 0.73 / 0.93 baseline.
  Do NOT tune the ranker to the new cases — measure, record, stop.

## Stop condition (explicit)

Stop when the queue above is done, **or** when the next task requires a human
decision, **or** on any failure not fixable inside one iteration. On stopping,
write the outcome here and do not reschedule. Do not invent further work — the
previous loop's honesty about stopping is the behaviour to copy.

## Per-iteration protocol

1. Read this file; take the first unchecked `[ ]`.
2. Build TDD-style: module self-tests, registered in `scripts/run_tests.sh`.
3. Run the **full** suite. Commit only if green. One logical change per commit.
4. Tick the box, commit this file too.
5. No push to `engine/entailment`. No new dependency. No model in any decision path.

## Log

- 2026-09-05 — worktree + branch created off `1a455f0`; baseline suite green;
  queue verified against the code rather than the stale plan doc.

---

## LOOP COMPLETE — 2026-09-05

Both queue items merged and green. The loop stopped because the queue is empty and
only human-gated items remain — it did not invent further work.

**Shipped on `loop/register-wiring` (full runner green at each step):**
- `7794185` **A1** — s.180 and s.184 as company-level register rows. Register
  13 → 15. Both carry `limbs_not_decided`, so neither can ever read SATISFIED.
  Two of my own tests asserted SATISFIED on an empty tuple; the engine was right
  and the tests were wrong — corrected to assert the undecided limbs are *named*.
- `4010c1a` **A2** — cross-section eval 45 → 70 cases, 37 → 62 sections reached.
  **p@1 0.71 (was 0.73), recall@5 0.91 (was 0.93).** Not tuned.

**What the re-measurement actually tells us:** the earlier 0.73/0.93 was not an
artefact of 45 friendly cases — the numbers held on a 56%-larger, harder set. The
six p@1 misses are one class: semantic near-neighbours a lexical ranker cannot
separate (s.14→467, s.169→242, s.271→376, plus the three known). That is the
measured case for the embedding layer, decision B, which the operator deferred.
It stays deferred; this loop did not reopen it.

**Not done, and correctly not done:**
- **H-B** — the `NEEDS_LAWYER` retrieval labels still need a lawyer.
- **H-C** — a practising CS still has not reacted to the evidence pack. This
  remains the highest-value open item in the whole project, and no amount of
  autonomous work moves it.

**To land this branch:**

    cd ~/PlacedOn/placedon-law-backend
    git log --oneline engine/entailment..loop/register-wiring   # read the diff
    git merge loop/register-wiring
    git worktree remove ~/.worktrees/placedon-loop              # when finished
