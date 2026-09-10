# Loop runbook — Bookmark / God's Eye foundations, v0

Pattern **`sequential`**, mode **`safe`**. Created 2026-09-11.
Implements [`PLAN_08_BOOKMARK_AND_GODSEYE.md`](PLAN_08_BOOKMARK_AND_GODSEYE.md)
**foundations only** — the shared algebra, the release chokepoint, the licence
axis, and the two live defects that document found. **No feed is ingested by this
loop.** Ring 2 and Ring 3 are gated behind H-E/H-F/H-G below.

## Pre-flight (2026-09-11)

| Check | Result |
|---|---|
| Branch / state | `loop/bookmark-godseye-v0`, cut clean from `main` @ `f2ebcb3` |
| Full suite before first iteration | **green** — `all suites green`, exit 0, run 2026-09-11 01:2x |
| `ECC_HOOK_PROFILE` not disabled | unset |
| Explicit stop condition | §4 |
| Secret scan on the diff | clean |
| Concurrent session in this tree | PID 19860 alive but idle, tree clean at cut |

### 0.1 — the pre-flight result, written down

```
$ ./scripts/run_tests.sh
...
all suites green
$ echo $?
0
```

Run on `loop/bookmark-godseye-v0` cut clean from `main` @ `f2ebcb3`, with a clean
working tree and no local modifications. A pre-flight whose result is not written
down is not a pre-flight.

---

## 0. Findings that shape this queue — read before building

### D-1 · The amendment corpus stops in 2023 (BLOCKS any backtest)

Amendment years present in `corpus/companies_act/` run 2014–2023 — 2022 has 2
records, 2023 has 1, and **2024, 2025, 2026 are entirely absent.**

Either the Act has not moved in three years, or the footnote ledger we hold is
stale. **Nothing is watching either way.** This is the G.S.R. 880(E) failure one
layer up: `as_of.py` can reconstruct a recent date from an incomplete amendment
record and return fidelity `EXACT`, because EXACT means "every span we know about
is accounted for", not "we know about every span."

The loop **measures and reports** this gap. It does **not** close it — closing it
means acquiring instruments, which is browser-gated and human-attested (H-D2).

### D-2 · `fusion.py`'s docstring overclaims by one sentence

McNemar on the module's own reported error sets (b=11, c=8) gives exact two-sided
**p = 0.648**; Wilson intervals on p@1 overlap ([0.61,0.82] vs [0.60,0.81]). So
"dense 0.73 beats BM25 0.71" is **not established at n=70**. The module's real
argument — near-disjoint error sets, so fusion helps — is structural and survives
untouched. Fix the one sentence; keep the argument.

### F-3 · There is no release chokepoint

"Only SERVABLE reaches a user" exists in six independent implementations under two
vocabularies (PLAN_08 §3). Anything new inherits none of it. T4 exists because of
this, and **no Ring 2 or Ring 3 work may begin until T4 lands.**

### F-4 · L-15 governs anything numeric

`.claude/memory/LESSONS.md:290-314`. A Bayesian engine was built here and deleted
because calibration was unreachable at the available n. `ECE_floor(0.9, 20) =
0.0535`, so a target of 0.05 is failed **by a perfect model**. The amendment
corpus gives n_eff ≈ 6 for "will Parliament amend", where the floor is 0.098 —
permanently dead. Ring 3's default output is therefore ordinal, not numeric.

---

## 1. Scope of this loop

**In:** the shared ordinal algebra; honest intervals; the two defects above; the
single release gate; the licence axis; and the calibration contract that decides
whether any number may ever be served.

**Out:** every feed (needs H-E and H-F). The observation store and `OBSERVATION`
class (needs T4+T5 and H-E). Vessel tracking (needs H-G, and PLAN_08 §5 says do
not). Any forecaster (needs T6 to return SERVABLE first, which it may not). The
timeline UI (design work, other repo).

---

## 2. Queue

- [x] **T0 — `checker/corpus_currency.py`: measure D-1, do not close it.**
  Report, per section and for the corpus as a whole, the latest amendment year we
  hold and the gap between it and a supplied `as_of`. Assert against the **ingested
  corpus**, never constants (house rule). Emits a finding shaped like
  `currency.report()`, in the same vocabulary, so it composes later.
  *Check (write first, must FAIL before): the corpus-level report names 2023 as the
  newest amendment year held and flags a ≥1-year gap against as_of 2026-09-11.*
  *Mutation: inject a synthetic 2025 amendment record into a fixture — the gap flag
  must clear. If it does not, the check is reading a constant, not the corpus.*

- [ ] **T1 — `checker/lattice.py`: the ordinal algebra, extracted.** ~90 LOC.
  One implementation of totally-ordered states + weakest-link composition + the
  **witness** (which input produced the result), so `currency` and `staleness` stop
  each growing a private `_SEVERITY`. Pure refactor; behaviour must not move.
  *Check: composing `(CURRENT, UNACQUIRED, SUPERSEDED)` returns `UNACQUIRED` AND
  names the input that produced it.*
  *Mutation: change `max` to `min` → returns `CURRENT`, check goes red. Second
  mutation: drop the witness → red on the name.*

- [ ] **T2 — `checker/interval.py`: Wilson, exact binomial, McNemar, seeded
  bootstrap.** ~110 LOC, stdlib only. Every proportion this repo already reports
  gets an honest error bar.
  *Check: `wilson(19, 20) == (0.764, 0.991)` to three decimals — the L-15 audit's
  own number, reproduced. The test IS the audit.*
  *Mutation: substitute the Wald form → `(0.854, 1.046)`, which both misses the
  value and exceeds 1.0. Red.*

- [ ] **T3 — Correct `fusion.py`'s docstring (D-2), using T2's McNemar.**
  One sentence. Keep the near-disjoint-error-sets argument; remove the unestablished
  comparative. Record the p-value in the docstring so nobody re-asserts it.
  *Check: the docstring no longer claims dense beats BM25; a test asserts
  `mcnemar(11, 8)` ≈ 0.648 so the correction is anchored to arithmetic, not taste.*

- [ ] **T4 — `checker/release.py`: ONE release gate, then migrate all six sites.**
  `may_release(*, evidence_state, licence, output_class, ring) -> Release`, where
  `Release` is frozen `(allowed: bool, reason: str)` — never a bare bool, because
  the reason is what the caller must show when it refuses.
  **One call site per commit**, each with a test proving behaviour is UNCHANGED.
  Sites: `evidence_pack.py:400`, `prescribed_thresholds.py:64`, `assessment.py:411`,
  `admission.py:55`, `event_log.py:105`, `s188_threshold.py:51`.
  *Check: an invariant test that enumerates the six sites and asserts each now
  routes through `release.may_release`; plus each site's existing tests still green.*
  *Mutation: make `may_release` return `allowed=True` unconditionally — at least
  three suites must go red. If fewer do, the gate is not load-bearing yet.*

- [ ] **T5 — `checker/licence.py`: Axis D.**
  Per-feed capability sets `{INTERNAL_ONLY, MAY_SHOW, MAY_STORE, MAY_DERIVE,
  EMBARGOED}` — a frozenset, **not** a ladder. Default for an unregistered feed is
  the **empty** set: may not even be computed with. Human-recorded contract
  reference and date; no default grants a right.
  *Check: an unregistered feed id yields the empty set and `may_release` refuses,
  naming the licence as the reason — not a 500, not a blank.*
  *Mutation: default an unknown feed to `{MAY_SHOW}` → the refusal test goes red.*

- [ ] **T6 — `checker/calibration_contract.py`: the module that settles it.** ~170 LOC.
  `TrackRecord`, `ece_floor(p,n)`, `n_min(p,eps)` from PLAN_08 §6, the state
  lattice (reusing T1, not a second scheme), and `render_number()` which raises
  unless the record is SERVABLE.
  *Check: a PERFECTLY calibrated synthetic forecaster at p=0.9, n=20 is **REFUSED**,
  and the refusal string quotes `floor 0.0535 > target 0.0500`. A perfect model
  failing the gate is the correct behaviour and the entire point of the module.*
  *Mutation: replace `n_min(p, eps)` with a constant 20 → the perfect forecaster is
  served. Red.*

---

## 3. Per-iteration cycle

```
1. take the top unchecked item
2. write its check FIRST; run it; it must FAIL
3. build the smallest thing that makes it pass
4. run the FULL suite: ./scripts/run_tests.sh  -> "all suites green"
5. register any new module in scripts/run_tests.sh (hardcoded array, no globbing)
6. mutation-test the check -- break what it exists to catch
7. one commit, message says WHY; push to this loop branch
8. tick the box here and commit this file too
```

House rules that bite, from `.claude/memory/CODING_CONVENTIONS.md`:
`_test()` lives in the module · print the literal `N/N passed` · **`raise
SystemExit(1)` on failure** (note `event_log.py:342` omits this — do not copy it) ·
assert against the ingested corpus, not constants · never read the clock, inject
`as_of`/`generated_at` · pin external state with the existing stub context managers.

---

## 4. Stop condition

Stop and report when **any** is true:

1. T0–T6 done, committed, pushed, full suite green.
2. The full suite goes red and cannot be made green inside one iteration.
3. Three consecutive iterations find nothing actionable.
4. A task can only be completed by acquiring or attesting an instrument, a feed, or
   a licence (H-D2 / H-E / H-F — all human-gated).
5. Any task would require inventing a statutory figure, date, instrument number,
   **price, position, or licence term.**
6. **T6 returns "not servable" for every proposed target.** That is a SUCCESS, not
   a failure: it means the honest answer is the ordinal lattice, and the loop stops
   rather than shopping for a target that clears the bar.

---

## 5. Hard limits — the loop may never

| Never | Why |
|---|---|
| Type in a statutory threshold, date or instrument number | Six documented incidents. Statute enters via `ingest_*`/`register_*` + `--attest` only |
| Type in a price, a vessel position, or a licence term | Same rule, new corpus. A fabricated observation is worse than a fabricated citation because nobody expects to check it |
| Run `--attest` | It certifies that a *person* checked. A self-attesting script defeats the design |
| Ingest ANY feed | Needs H-E (governance) and H-F (licence attestation). Not this loop |
| Let a Ring 0 module import from Ring 2 or Ring 3 | A forecast reaching a decider destroys "a wrong model cannot make the product wrong" — silently, because the output still looks deterministic |
| Register a feed with a non-empty default licence | Fail closed. An unregistered feed may not even be computed with |
| Widen `metric_policy.evaluate_gate` to admit a continuous score | Its whole argument is that four specific axes stop a useless configuration passing |
| Emit a bare number | PLAN_08 §6. Interval, n, base rate, and skill-vs-baseline, or an ordinal grade |
| Add a third-party dependency | The engine has zero, deliberately |
| Describe any vendor as "MCA-authorized" | No such claim could be verified against any published MCA list |
| Commit a key, customer name, or a lawyer's details | — |

---

## 6. Human-gated — NOT in this loop

- **H-E — the governance amendment.** `CLAUDE.md:39-40` is a **closed enumeration**
  of five permitted sources; public registers and market feeds are none of them, and
  `SOURCE_POLICY.md`'s layer table has no row that could support them. Adding a
  source class is a founder decision, made explicitly and dated. **That paragraph is
  the moat being modified** — draft it before any feed work.
- **H-F — per-feed licence attestation.** A human reads the contract and records
  what it permits, with reference and date. Feed-level attestation is a real
  weakening of the two-human-check design and PLAN_08 §4 says so; it must not
  quietly wear the costume of instrument-level attestation.
- **H-G — the AIS budget decision.** Omit vessel tracking, or fund it honestly at
  ~$2,000/month minimum. There is no third option that is global, real-time and
  redistribution-clean. PLAN_08 §5 recommends omitting it.
- **H-D2 — acquire the missing 2024–2026 amendments** once T0 measures the gap.
  Browser download → `scripts/register_*.py` → human `--attest`.
- **H-B** — a lawyer resolves the `NEEDS_LAWYER` retrieval labels.
- **H-C** — a practising Company Secretary reacts to the evidence pack
  (`docs/H001_OUTREACH.md`). **Still the highest-value open item in the project**,
  and everything in PLAN_08 is ahead of it. No autonomous work moves it.
