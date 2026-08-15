# Loop runbook — corporate & financial compliance engine

Created 2026-08-15. Pattern **`sequential`**, mode **`safe`**.
Supersedes `.claude/plans/loop-runbook.md` for scope; two items carry forward (§3 items 6–7).
Implements the build order in `docs/TECHNICAL_PLAN_CORPORATE.md` §6.

## Pre-flight — all four passed

| Check | Result |
|---|---|
| Tests pass before first iteration | `scripts/verify.py` → **GO, 50 checks** |
| `ECC_HOOK_PROFILE` not disabled | unset — not disabled |
| Explicit stop condition | §4 |
| Repo state | `main`, clean, `22e73ac`, 0 ahead / 0 behind |

## 1. Why this loop is different from the last one

The previous runbook opened by admitting its ceiling: every queued item was downstream of Gate 1, so
the loop was maintenance rather than progress, and it said so.

**That is no longer true.** Steps 1 and 2 below — `deadlines.py` and the `DerivedDate` verifier rule
— require **no corpus, no lawyer, and no customer**. They are pure arithmetic and a mutation test.
Steps 3–7 need the corpus but not verification.

Only step 8 (`verified_by`) needs a human, and it is deliberately last.

**So this loop can genuinely build.** The honest caveat is unchanged and belongs here anyway: **zero
Company Secretaries have been interviewed.** The loop can build the engine; it cannot tell you
whether anyone wants it.

## 2. Branch strategy

Commit directly to `main`, as this repo does. No CI, no PR workflow, no second contributor —
`continuous-pr` would add ceremony with no reviewer. The real gate is `scripts/verify.py`, run before
every commit, blocking on NO-GO. Push after each green iteration.

## 3. Queue

### 1 — `checker/deadlines.py` with `DerivedDate` · **no corpus needed, start here**

Pure functions, no model, no network. Same shape as `distress.py`: deterministic, self-testing,
runnable directly.

- `DerivedDate` carrying `result, anchor, anchor_label, interval_text, interval, citation, quote`
- `compute()`, `applicable()`, `calendar()`
- **Tests first, against fixtures, and they must FAIL before they pass**
- Cover the named traps from the technical plan §1: first-AGM nine-months rule, the three
  simultaneous AGM constraints, s.92/s.137 anchoring to the AGM's **actual** date

### 2 — Verifier `DerivedDate` rule + **mutation test** · gates everything after it

A `DerivedDate` is admissible **iff** `interval_text` appears verbatim in the cited provision **and**
re-running the arithmetic reproduces `result` exactly.

- **Mutation-test it**: change `interval_text` to a phrase not in the provision, confirm the check
  FAILS, restore. Then change the arithmetic, confirm FAIL, restore.
- A bare date with no derivation must still be rejected.

**If this design does not survive its own mutation test, stop and hand back. Nothing downstream is
worth building on a verifier that cannot catch a wrong interval.**

### 3 — `scripts/ingest_companies_act.py`, six sections

s.96, s.92, s.137, s.134, s.173, s.2(85). India Code, **byte-verified**. Hand-typing statute remains
barred. `check_transcription.py` extended. **`source_quality` set on every provision at ingest.**

Replace the four existing MCA provisions (`secondary_reproduction`, one `DISPUTED`) with primary
text — do not append.

### 4 — Wire rules to corpus

Every rule's `interval_text` must resolve verbatim in the ingested provision **or raise at load
time**, exactly as `register.py` raises on `DATE_NOTIFIED` without `reply_verbatim`.

### 5 — `CompanyFacts` into `applicability.py`

Thresholds for s.2(85) small company, s.2(62) OPC, s.135 CSR. Decided deterministically; the model
never touches this. Figures come from the ingested definition, never from memory.

### 6 — `conflicts()` over the three AGM constraints

The operative date is the earliest, and the **disagreement must be reported**, not silently resolved
to the minimum. Same failure `ARCHITECTURE.md` §3 describes for s.9.

### 7 — `bench_answers.py` + 20 corporate questions; **re-run `bench_retrieval.py`**

Three numbers as always: fabrication, coverage, wrong abstention. And the retrieval check —
`ARCHITECTURE.md` §5 says keyword-and-scan is "correct at 30 sections and wrong somewhere around
500". This lands near 100 with far denser cross-referencing. **If recall@3 falls below 1.00, stop
and report — do not silently switch to embeddings.**

### 8 — Model router · added 2026-08-16

From the pasted AI master plan. The idea is right: route to the cheapest model that suffices,
*because the engine has already decided the answer*. The ₹ figures in that plan are wrong; the
mechanism is not.

- Route by task class, not by prompt length
- **Use measured costs** — Haiku ₹0.97, Sonnet ₹2.91 on this workload, not the plan's ₹0.38/₹1.49
- **Verify every model identifier against the registry before it enters code.** Six wrong
  identifiers were found in the pasted plans; `PROVIDER_DECISION.md` §7 records three earlier ones.
  This check is one command and it is the cheapest verification in the project.
- **Do not add GPT-4o or DeepSeek.** Two more vendors and keys, for a document-parsing feature whose
  feasibility is still being researched. Wait for that result.
- Add a `verify.py` check: **every model name in the codebase must exist in `PRICING`**, so an
  invented identifier cannot ship.

### 9 — Prompt caching on the statutory context

Largest single cost lever available and it is architectural: the 6,700-token context is **immutable
statutory text**, and prompts repeat across users. Measure the saving with `bench_answers.py`; do
not assert it.

### 10 — Free tier as a capability boundary, not a usage cap

Per `../placedon-law-research/docs/PLAN_AUDIT_2026_08_16.md` §4. Everything the deterministic engine
does is **₹0 per call forever** — applicability, deadlines, section lookup, `trace()`, `conflicts()`,
the register, the distress route. Those are free and uncapped. The model-calling paths — narration,
document analysis, exported reports — are paid.

**Do not implement a per-user query counter.** It is the wrong shape and it would gate work that
costs nothing to serve.

**Blocked on Gate 1**: today the engine abstains on everything, so a free tier would give away a
refusal.

### Carried forward from the previous runbook

**6 — CORS allow-list omits `placedon.com`.** `checker/app.py:53-55` lists `placedon-hr.vercel.app`
and a preview regex, but not the apex domain (resolves to Vercel at `76.76.21.21`). Still a real
production bug and still the last live "hr" naming.

**7 — `source_quality` unset on all 30 PoSH sections**, while all 14 Rules carry
`secondary_reproduction_cross_verified`. Missing, not false — but the new corpus must not repeat it.

## 4. Stop condition

Stop and report when **any** is true:

1. Steps 1–7 are done, green, committed and pushed.
2. **Step 2's mutation test fails** — the `DerivedDate` design is wrong and that is a design
   decision, not a loop decision.
3. **`bench_retrieval.py` recall@3 drops below 1.00** at step 7 — reopening the embeddings question
   is a decision for a person.
4. `verify.py` returns NO-GO on two consecutive iterations.
5. Three consecutive iterations find nothing actionable.
6. Step 8 is reached — `verified_by` needs a human.

## 5. Hard limits

| Never | Why |
|---|---|
| **Write `verified_by` on any provision** | It records that a **named professional** checked our reading. A loop writing it is the product's central lie. |
| **Hand-type statutory text** | Six documented instances of a typed version silently dropping a clause, including s.4(2)(c) losing the one-half-women proviso. |
| **Relax the verifier to let bare dates through** | This is the exact failure `TECHNICAL_PLAN_CORPORATE.md` §0 exists to prevent. |
| **Add a confidence float or a distress score** | Refused eight times, latterly with evidence. |
| **Ship a `verify.py` check without mutation-testing it** | Four vacuous checks have shipped here already. Break what it guards, confirm failure, restore. |
| **Delete or gate `distress.py`** | ₹0, model-free, not contingent on commercial scope. |
| **Switch to embeddings without re-running the benchmark** | The only way this repo has ever changed its mind is a measurement. |
| **Add a paid API or dependency** | ₹3,500/month cap. Inference spend is ₹0.00. |
| **Duplicate the three running research agents** | They are covering MCA enforcement orders, legal-AI papers, and CS practitioner/competitor research. Do not re-research those. |

## 6. Per-iteration cycle

```
1. python3 scripts/verify.py          # must be GO before starting
2. take the top open item from §3
3. write the test FIRST — it must FAIL
4. implement until it passes
5. mutation-test any new verify.py check: break the guarded thing,
   confirm the check FAILS, restore. Note: `git checkout <file>`
   reverts the WHOLE file — stash or re-apply deliberately.
6. python3 scripts/verify.py          # must be GO
7. commit — the message names what broke and why the check exists
8. git push
```

Step 5 is not optional.

## 7. Start and monitor

```bash
cd /Users/nishantsingh/PlacedOn/placedon-law-backend

/loop                                              # start, dynamic pacing

python3 scripts/verify.py | tail -1                # GO / NO-GO and count
python3 checker/deadlines.py                       # once step 1 lands
python3 scripts/bench_retrieval.py                 # the step-7 tripwire
git log --oneline origin/main..HEAD                # unpushed iterations
cat .claude/plans/loop-runbook-corporate.md        # this file

/loop stop
```

## 8. The one line

> This loop can build the engine end to end without a lawyer or a customer. It still cannot tell you
> whether a Company Secretary wants it — that is ten conversations, and they remain at zero.
