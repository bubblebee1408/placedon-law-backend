# Loop runbook — Company Event Log v0

Pattern **`sequential`**, mode **`safe`**. Created 2026-09-09.
Implements [`COMPANY_EVENT_LOG_SPEC.md`](../../Placedon-law-business-plan/docs/COMPANY_EVENT_LOG_SPEC.md) §7 **v0 only** —
the *law-change* log, on data we already hold. Company-fact events are v1 and wait on licensed data.

> Runbook lives in `docs/`, beside the spec it implements, per the project convention: a runbook
> nobody can read is not a runbook.

## Pre-flight (run 2026-09-09)

| Check | Result |
|---|---|
| Branch / state | `main`, clean, synced with `origin/main` @ `8df7919` |
| Full suite before first iteration | **green** — every suite, `./scripts/run_tests.sh` |
| `ECC_HOOK_PROFILE` not disabled | unset |
| Explicit stop condition | §4 |
| Spec-referenced modules present | all 10 present in `checker/` |
| Secret scan | clean |

## 0. Two findings from pre-flight — read before building

### F-1 · Two obligations have no declared currency basis (blocks v0)

`currency.report()` returns **UNDECLARED** for `CA13-S180-BORROWING-LIMIT` and
`CA13-S184-DIRECTOR-INTEREST`. Both were added to the register by the previous loop
(13 → 15 rows) without a matching `Dependency` in `currency.DEPENDENCIES`.

This is the currency map catching its own gap — working as designed. But an event log built on
top of it today would emit two `BASIS_UNACQUIRED` events that say nothing about a company and
everything about our map. **Fix before deriving any event.** → **T0**

### F-2 · The s.2(85) chain on record is one instrument deep — HUMAN-GATED

`prescribed_thresholds` holds exactly one prescribed small-company instrument:
**G.S.R. 700(E), 2022-09-15** (₹4cr / ₹40cr, CORROBORATED, attested reviewer NS).

The spec's own golden fixture (§8) asks for the chain **₹50L → ₹2cr → ₹4cr → ₹10cr** across
**G.S.R. 92(E) / 700(E) / 880(E)**. Two of those three are **not on record**:

- **G.S.R. 92(E) (2021, ₹2cr)** — absent. Any `as_of` in 2021 returns `UNACQUIRED`, not ₹2cr.
  Cost of absence: historic point-in-time queries are refused. Correct, but incomplete.
- **G.S.R. 880(E) (2025, ₹10cr)** — absent, and this one is load-bearing. If that instrument is
  real and in force, the engine today serves ₹4cr as **CURRENT** when the true state is
  **SUPERSEDED**. That is precisely the one failure the spec names as unacceptable (§8):
  *never render `CURRENT` on a superseded instrument.*

### F-2, RESOLVED 2026-09-09 — the instrument is real and the bug was live

Checked whether 880(E) *exists* (research, not acquisition — the loop may read, it may not
attest). **It exists.** G.S.R. 880(E), Companies (Specification of Definition Details) Amendment
Rules 2025, dated **01-12-2025**, raises the limits to **₹10 crore / ₹100 crore**, in force from
publication. So the engine *was* serving ₹4 crore as CURRENT on every date after 01-12-2025.

Fixed in `172ba86`, without typing the new law into the answer path:

- 700(E)'s window now closes 30-11-2025 — its figures still answer their own period, nothing later;
- 880(E) is the governing record from 01-12-2025, **unservable** until acquired and attested;
- so every prescribed small-company amount from 01-12-2025 is **REFUSED**, naming the instrument
  to acquire — it does not fall back to the superseded figure. Falling back is not the cautious
  answer: a company with ₹6 crore capital is small under 880(E) and not small under 700(E).

₹10cr/₹100cr sit in `prescribed_thresholds` as a **claim to be checked, not a fact**. Their only
provenance is secondary reporting, which may not be served; `register_gsr880e.py`'s clause regex
requires the downloaded Gazette artifact to carry those words and refuses loudly otherwise.

**H-D is now the highest-priority human task** (§6): download the artifact and attest it. Until
then the engine refuses today's small-company classification — correct, and visibly incomplete.

## 1. Scope of this loop

**In:** the `Event` type, law-change event derivation from `currency`, the read API, and the
correctness test. All composition of parts already built and green.

**Out:** company-fact events (needs licensed MCA data — v1); subscriptions/push (v1); the
timeline UI (lives in the public business-plan repo, and is design work, not loop work);
the persistent bitemporal store (v2).

## 2. Queue

- [x] **T0 — Declare the currency basis for s.180 and s.184.**
  Add two `Dependency` rows to `checker/currency.py`. Both rest on Act text held verbatim
  (no delegated rule), so both are Act-only dependencies — same shape as s.185/s.186.
  *Check (write first, must FAIL before): `currency.report(any date)` returns **zero**
  `UNDECLARED` findings, and `len(report()) == len(REGISTER) == 15`.*
  *Mutation: delete one Dependency again — the check must go red.*

- [x] **T1 — `checker/event_log.py`: the `Event` type.**
  Frozen dataclass per spec §2.3 with `EventKind`, `OutputClass`, `CurrencyState`; bitemporal
  `at` (valid time) vs `known_at` (transaction time); `source` carrying instrument ref + sha256;
  `verified_by is None ⇒ OutputClass.SIGNAL`, enforced in `__post_init__`, never a hidden fact.
  Deterministic `id` = hash of the identifying fields, so the same event re-derives to the same id.
  *Check: an Event with `verified_by=None` and `output_class=VERIFIED_FACT` **raises**;
  re-deriving an identical event yields an identical `id`.*

- [x] **T2 — Law-change event derivation.**
  `events_for(as_of, since=None) -> list[Event]` mapping `currency.report/stale` onto Events:
  `CURRENT`→ no event · `SUPERSEDED`→ `OBLIGATION_SUPERSEDED` · `UNACQUIRED`→ `BASIS_UNACQUIRED`
  · `NOT_YET_IN_FORCE`→ `OBLIGATION_NOW_IN_FORCE` (dated to commencement) · a threshold whose
  `effective_from` falls in the window → `THRESHOLD_MOVED`.
  Every Event carries its instrument + date; `consequence` computed deterministically or `None`.
  *Check: golden fixture on the instrument actually on record — as_of 2022-09-16 yields a
  `THRESHOLD_MOVED` event citing G.S.R. 700(E) dated 2022-09-15; as_of 2022-09-14 does not.
  No event is ever emitted without a source.*

- [x] **T3 — Wire the read API.**
  Extend `checker/api.handle()` (pure function, no server) with
  `GET /v1/company/{cin}/events?as_of=&since=&kind=&class=`, `GET /v1/company/{cin}/events/{id}`,
  `GET /v1/instruments/{gsr}/affected`. Fails closed on a bad date or unknown route, same shape as
  the existing `POST /v1/compliance-pack`.
  *Check: a malformed `as_of` returns 400, not a guess; an unknown event id returns 404;
  `/v1/instruments/700/affected` returns `CA13-S2-85-SMALL`.*

- [x] **T4 — The one correctness metric, as a test that can fail.**
  *Never render `CURRENT` on a superseded instrument.* Assert it directly, then **mutation-test
  it**: register a synthetic newer unservable instrument in a fixture and confirm the event log
  flips to `OBLIGATION_SUPERSEDED` and the API stops saying CURRENT.
  *A check that survives its own mutation is decoration — this one must catch it.*

## 3. Per-iteration cycle

```
1. take the top unchecked item
2. write its check FIRST; run it; it must FAIL
3. build the smallest thing that makes it pass
4. run the FULL suite: ./scripts/run_tests.sh  -> "all suites green"
5. register any new module in scripts/run_tests.sh
6. mutation-test the check (step 5 of docs/LOOP.md) -- break what it exists to catch
7. one commit, message says WHY; push to a loop branch
8. tick the box here and commit this file too
```

## 4. Stop condition

Stop and report when **any** is true:

1. T0–T4 done, committed, pushed, full suite green.
2. The full suite goes red and cannot be made green inside one iteration.
3. Three consecutive iterations find nothing actionable.
4. A task can only be completed by acquiring or attesting an instrument (that is H-D, human-gated).
5. Any task would require inventing a statutory figure, date, or instrument number.

## 5. Hard limits — the loop may never

| Never | Why |
|---|---|
| Type in a statutory threshold, date or instrument number | Six documented incidents of hand-typed statute silently dropping clauses. Statute enters via `ingest_*`/`register_*` + `--attest` only |
| Run `--attest` | It certifies that a *person* checked identity and verbatim text. A self-attesting script defeats the design |
| Loosen the verification gate to make a row green | Narrowing-only verifier changes. Coverage starts at 0% by design |
| Add a third-party dependency | The engine has zero, deliberately. A new one needs a measured reason |
| Put a model in the event pipeline | Spec §3: the model may phrase a title; it never creates an event, date or consequence |
| Commit a key, customer name, or a lawyer's details | — |

## 6. Human-gated — NOT in this loop

- **H-D — acquire and attest G.S.R. 880(E).** Confirmed real (F-2); the engine now refuses
  today's small-company classification until it is held. One command after the download:
  `python3 scripts/register_gsr880e.py <file>` then `--attest <reviewer-id>`. This is the
  highest-priority human task in the project after H-C.
- **H-E — acquire G.S.R. 92(E) (2021, ₹2cr)**, optional. Without it, point-in-time queries in the
  2021 window refuse rather than answer. Correct, but incomplete.
- **H-B** — a lawyer resolves the `NEEDS_LAWYER` retrieval labels.
- **H-C** — a practising Company Secretary reacts to the evidence pack (`docs/H001_OUTREACH.md`).
  Still the highest-value open item in the project; no autonomous work moves it.


## 7. Outcome — loop closed 2026-09-09

All five queue items done, committed, pushed; full suite green throughout.

| Commit | What |
|---|---|
| `6ec53f3` | T0 — s.180/s.184 currency basis declared; the UNDECLARED gap closed |
| `172ba86` | **F-2 — the supersession bug.** 700(E) window closed, 880(E) staged unservable, five suites corrected, guard mutation-tested twice |
| `2a3101e` | T1–T4 — `event_log.py` and the three read routes |

**The finding worth carrying forward:** the loop's first regression guard *survived its own
mutation*. It asserted the currency status was not `CURRENT`; with the bug reintroduced the status
read `SUPERSEDED`, which satisfied it, while the engine went on serving ₹4 crore. A check that
survives its own mutation is decoration. It now asserts the amount is **refused**, and fails with
the served figures named. Step 6 of §3 is the step that caught it.

**Not built, deliberately:** the timeline UI (design work, and it lives in the public repo),
subscriptions/push, company-fact events, and the persistent bitemporal store — all correctly v1/v2.
