# Loop runbook — the intelligence core, v0

Pattern **`sequential`**, mode **`safe`**. Created 2026-09-12.
Successor to [`LOOP_BOOKMARK_V0.md`](LOOP_BOOKMARK_V0.md) (T0–T6, complete, PR #5).

## The principle this queue is selected by

The features are not decided. H-E (the governance amendment), H-G (the AIS
budget) and above all **H-C** (one Company Secretary reacting to the pack) are all
open, and the founder has chosen to keep building while they are.

That choice is only defensible if the building is **decision-invariant**: work
that pays off under *every* branch of the feature decision. So the test each item
must pass before entering this queue is one question —

> **If the feature decision goes the other way, is this still needed?**

If the answer is no, it does not go in, however cheap it looks. That rule is what
keeps this from becoming a fourth speculative layer on an unvalidated core, which
`BLOOMBERG_FOR_INDIA_ANALYSIS.md` §6 names as this project's largest historical
risk.

**Build the floor, not the rooms.** The later re-architecture the founder
anticipates -- integrating whatever features win -- is cheap if and only if the
seams exist. So build seams, never implementations of features nobody has
confirmed. A seam costs little if unused; a feature built for a wedge that does
not survive costs everything it took to build.

### What this rule EXCLUDES, explicitly

Recorded so the exclusions are visible rather than quietly skipped:

- `OBSERVATION` / `ESTIMATE` output classes — designed in PLAN_08 §4, **not built**.
  No feature needs them yet, and a class with no caller acquires no invariant.
- Any feed adapter (needs H-E and H-F).
- Extending `entity_graph` to CIN/DIN — cheap, and still only pays off if Bookmark
  wins. `corporate_data.py` already keys on CIN/DIN where it matters.
- Any forecaster. `calibration_contract` refuses the one that was asked for.

## Pre-flight (2026-09-12)

| Check | Result |
|---|---|
| Branch | cut from `loop/bookmark-godseye-v0` after `bc94c3a` |
| Full suite before first iteration | **green** — `all suites green`, exit 0 |
| `ECC_HOOK_PROFILE` not disabled | unset |
| Explicit stop condition | §4 |
| Concurrent session in this tree | PID 19860 still alive — see §5 |

---

## 1. Queue

- [ ] **U0 — `checker/rings.py`: the firewall, enforced by AST.**
  Declare every module's ring (0 legal core, 1 bookmark, 2 observation, 3 inference).
  `_test()` walks each Ring 0 module's AST and fails on an import from a higher
  ring. **Install it now, while there is nothing to violate it** — a firewall added
  after the first breach is archaeology, not architecture.
  *Decision-invariant because:* whichever features land, Ring 0 must stay
  deterministic, and that property is only credible if a machine checks it.
  *Check: a synthetic Ring 0 module importing a Ring 3 name fails the test, naming
  both modules and both rings.*
  *Mutation: delete the ring comparison — the synthetic violation passes. Red.*

- [ ] **U1 — `checker/pending.py`: watch what is scheduled, never serve it.**
  A dated, sourced record of legislation that is *proposed but not law*, with an
  explicit `NOT_LAW` state that cannot be promoted by any code path. Seeded from
  `corpus_currency.AMENDMENT_LEADS` — which today means the Corporate Laws
  (Amendment) Bill, 2026, 107 clauses, before a Joint Committee.
  *Decision-invariant because:* every feature benefits from knowing the law is
  about to move, and `staleness.py` already concedes "Discovery of a successor is
  human." This is the cheapest honest improvement to that.
  *Check: a pending item can never reach `currency.report()` or any servable path;
  a test asserts no code path promotes NOT_LAW to an in-force state.*
  *Mutation: allow promotion — the amendment ledger gains a Bill that is not law. Red.*

- [ ] **U2 — extract the acquisition pipeline from five copies.**
  `register_gsr700e`, `register_gsr880e`, `register_kmp_rules`,
  `register_s188_rule15` and `register_sebi_lodr` are one shape copy-pasted five
  times: identity regex → sibling rejection → clause capture → sha256 → record →
  two-human `--attest`. Extract it; keep each script's *instrument-specific*
  patterns local, because those are the part that must not be shared.
  *Decision-invariant because:* every future source, whichever features win, is
  acquired this way. Five copies means the sixth diverges.
  *Check: all five existing registrations still classify identically — byte-for-byte
  on their own fixtures — after the extraction.*
  *Mutation: weaken the sibling-rejection in the shared layer; at least two
  scripts must go red, proving the shared layer is load-bearing rather than decorative.*

- [ ] **U3 — finish T4: the three gates that did NOT move.**
  `assessment.servable_conclusion`, `admission.ready_for_production` and
  `event_log`'s verifier invariant ask genuinely different questions and were
  registered rather than migrated. Decide, per gate and in writing, whether it
  should route through `release.may_release` or stay separate — and record the
  reason either way in `release.GATES`.
  *Decision-invariant because:* it is the completion of a refactor already shipped
  half-done, and a registry whose entries nobody revisited is a to-do list wearing
  a data structure.
  *Check: every `Gate` carries an explicit `routed: bool` and a reason; the
  invariant test asserts no gate is left undecided.*

- [ ] **U4 — wire `interval` into every published proportion.**
  `metric_policy` reports precision/recall/F1, `reranker` reports held-out numbers,
  the benchmark reports p@1 — all as bare figures. Attach Wilson intervals.
  *Decision-invariant because:* every number this project publishes is read by
  someone deciding whether to believe it, under all futures.
  *Check: `metric_policy`'s report carries an interval beside every proportion, and
  a bucket too small to support one says so rather than printing a spurious range.*
  *Mutation: return the point estimate as both bounds — the "too small to support
  one" check must go red.*

---

## 2. Per-iteration cycle

Unchanged from `LOOP_BOOKMARK_V0.md` §3. Check first and it must FAIL; smallest
thing that passes; full suite; register in `scripts/run_tests.sh`; mutation-test
the check; one commit saying WHY; push; tick the box.

House rules that bite: `_test()` in the module · print `N/N passed` · **`raise
SystemExit(1)` on failure** · assert against the ingested corpus, not constants ·
never read the clock · pin external state with the stub context managers.

---

## 3. What this loop is NOT for

It does not decide features. It does not touch the wedge. If a task in it starts
to feel like it is choosing a product direction, that is the signal to stop and
put the question to a person — which is §4.4.

---

## 4. Stop condition

Stop and report when **any** is true:

1. U0–U4 done, committed, pushed, full suite green.
2. The suite goes red and cannot be made green inside one iteration.
3. Three consecutive iterations find nothing actionable.
4. **A task can only be completed by deciding a feature.** That is H-C/H-E/H-G and
   belongs to a person.
5. Any task would require inventing a statutory figure, date, instrument number,
   price, position, or licence term.
6. H-C closes. **A practitioner's reaction outranks this entire queue**, and the
   right response to it arriving is to stop and re-plan, not to finish U4 first.

---

## 5. Hard limits — the loop may never

Inherits every limit in `LOOP_BOOKMARK_V0.md` §5. Additionally:

| Never | Why |
|---|---|
| Build an `OBSERVATION` or `ESTIMATE` class with no caller | A class with no caller acquires no invariant, and ships the vocabulary without the discipline |
| Let a Ring 0 module import from Ring 2 or 3 | U0 exists to make this mechanical rather than remembered |
| Promote anything in `pending.py` to in-force | A Bill is not law. Six of this project's documented incidents are a version of this error |
| Build a feature because it is cheap | Cheapness is not decision-invariance. §1's question is the only test |

**Working-tree hazard:** a second session (PID 19860) has been committing into this
tree for five days and has twice swept uncommitted work into its own commits.
Before starting, either close it or move this loop to `git worktree`. This is the
one failure mode that silently destroys work rather than turning a test red.

---

## 6. Human-gated — unchanged, and still ahead of everything here

**H-C** — one practising Company Secretary reacts to the evidence pack. Draft
message ready in `docs/H001_OUTREACH.md`; it needs sending, not writing.
**H-D2** — confirm at India Code that no Companies Act amendment commenced after
2023-10-30. Research suggests this is a *negative to confirm* rather than a hunt;
leads in `corpus_currency.AMENDMENT_LEADS`.
**H-E** — the governance amendment to `CLAUDE.md`'s closed source list.
**H-F** — per-feed licence attestation. **H-G** — the AIS budget decision.
**H-B** — a lawyer resolves the `NEEDS_LAWYER` retrieval labels.
