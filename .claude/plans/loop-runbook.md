# Loop runbook — placedon-law-backend

Created 2026-08-12. Pattern **`sequential`**, mode **`safe`**.

## Pre-flight (all three passed at creation)

| Check | Result |
|---|---|
| Tests pass before first iteration | `scripts/verify.py` → **GO, 50 checks** |
| `ECC_HOOK_PROFILE` not disabled globally | unset — not disabled |
| Explicit stop condition | §4 below |

Repo: `main`, clean, `10f94cc`, 0 ahead / 0 behind `origin/main`.

---

## 1. Why `sequential` and not `infinite`

`infinite` is the wrong pattern for this repository right now, and the reason is worth stating
rather than discovering at iteration 40.

**The work that matters is human-blocked.** `verified_by` is null on all 30 PoSH sections, so the
Q&A path abstains on every question. Coverage is 0% and one evening of a lawyer's time takes it to
85% (`bench_answers.py`). No amount of autonomous iteration moves that number — the loop cannot
verify a section, because the entire point of `verified_by` is that a named human with a bar number
did it.

So the loop's ceiling is **maintenance, not progress toward launch.** An `infinite` loop over a
queue this size would exhaust the real items in a few iterations and then start inventing work,
which on a legal-compliance product means inventing scope. `sequential` with a finite queue and a
stop condition is honest about the ceiling.

**Do not read loop activity as progress.** The three numbers that matter (fabrication, coverage,
wrong abstention) are unchanged by everything in §3.

## 2. Branch strategy

Commit directly to `main`, as this repo already does — there is no CI, no PR workflow, and no
second contributor, so `continuous-pr` would add ceremony without a reviewer. The real gate is
`scripts/verify.py`, which runs before every commit and blocks on NO-GO.

Push after each green iteration. `origin` is `bubblebee1408/placedon-law-backend` (private).

## 3. Queue, re-derived from the working tree

Ordered by blast radius, not by the order in `docs/LOOP.md`. Item 0 is new — found during
pre-flight, not previously queued.

### 0 — CORS allow-list omits `placedon.com` · **not in docs/LOOP.md**

`checker/app.py:53-55` allow-lists `placedon-hr.vercel.app`, `placedon-hr-app.vercel.app`, and a
preview regex ending `-placeon.vercel.app`. The apex domain **`placedon.com` is absent** — verified
resolving to Vercel at `76.76.21.21`.

The front door (item 7 in `docs/LOOP.md`) cannot call this API from a browser until it is added.
Every request from the real domain fails CORS preflight. This is also the last live reference to
the retired "hr" naming.

- Add `https://placedon.com` and `https://www.placedon.com`
- Decide the `placedon-hr*` entries: keep only if those deployments still serve, else delete
- Check: production origins stay an explicit allow-list, never a bare pattern

### 1 — `NO_REPLY` unreachable from the CLI · `docs/LOOP.md` item 4

The register schema permits `NO_REPLY`; `scripts/build_register.py` has no flag that sets it. A
status the schema allows must be reachable by some code path, or the schema is describing a state
the system cannot enter.

- `--mark-no-reply CODE --on DATE`, refusing if `asked_on` is unset or under 30 days old
- Bengaluru Urban was asked **2026-08-12**, so nothing is eligible until 2026-09-11. The flag ships
  before it is needed; that is fine, and the 30-day refusal must be tested with a fixed date rather
  than "today"

### 2 — Dev CORS origin · `docs/LOOP.md` item 3

`http://localhost:*` and `http://127.0.0.1:*` in dev only. Folds naturally into item 0 — same file,
same allow-list, one review.

### 3 — Gazette text for the four MCA provisions · `docs/LOOP.md` item 5

Measured at pre-flight: `companies_accounts_rules_2014.json` is
`{secondary_reproduction: 2, secondary_reproduction_paraphrase: 1, DISPUTED: 1}`. Four provisions,
none Gazette-sourced, one actively disputed.

- Replace with Gazette text, set `source_quality`
- Check: `check_transcription.py` must cover them the way it covers the Act
- **Bar:** hand-typing statute is forbidden (`docs/LOOP.md` §"Why hand-typed statute is barred").
  Ingest from a primary source or leave it `DISPUTED` and honest.

### 4 — `source_quality` unset on all 30 PoSH sections

Also found at pre-flight. `posh_act_2013.json` has `source_quality: unset` on every provision,
while `posh_rules_2013.json` carries `secondary_reproduction_cross_verified` on all 14. The Act's
text is byte-verified against India Code, so the field is *missing*, not *false* — but a null
provenance field on the load-bearing corpus is exactly the shape of gap this project keeps finding.

Establish what the Act's 30 sections should carry, set it, and let `verify.py` assert it is never
null again.

### Deferred, deliberately

`docs/LOOP.md` items 6 (Companies Act s.96), 7 (`placedon.com` front door) and 8 (golden set).
Item 8 is the valuable one and is blocked: a golden set scored against a corpus that abstains on
everything measures the abstention, not the answers. It becomes worth building the day Gate 1
clears, and not before.

## 4. Stop condition

Stop and report when **any** of these is true:

1. Items 0–4 are done, committed green, and pushed.
2. `scripts/verify.py` returns NO-GO on two consecutive iterations — a ratchet that will not go
   green is a design problem, not a loop problem, and the loop must hand it back.
3. Three consecutive iterations find nothing actionable.
4. The only remaining work is in §5.

## 5. Hard limits — the loop must never do these

| Never | Why |
|---|---|
| Write `verified_by` on any provision | It records that a **named human with a bar number** checked our reading. A loop writing it is the product's central lie. |
| Send email, or mark the register `ASKED`/`ANSWERED` | 30 District Officer letters sit rendered in `outbox/`. Sending is the user's, and the register must only record what actually happened. |
| Hand-type statutory text | See §3 item 3. Six documented instances of typed statute silently dropping a proviso. |
| Add a confidence float, or a distress score | Refused eight times, latterly with evidence (`bench_safety.py`). |
| Deploy, or touch pricing | Gate 1 has not cleared; the product still abstains on everything. |
| Add a paid API or dependency | ₹3,500/month cap. Inference spend is ₹0.00 and every commit should keep it there. |

## 6. Per-iteration cycle

```
1. python3 scripts/verify.py          # must be GO before starting
2. take the top open item from §3
3. write the test first — it must FAIL
4. implement until it passes
5. mutation-test any new verify.py check: break the thing it guards,
   confirm the check FAILS, restore. A check that passes on broken
   code is worse than no check. (Four have shipped vacuous here.)
6. python3 scripts/verify.py          # must be GO
7. commit — message names what broke and why the check exists
8. git push
```

Step 5 is not optional. `git checkout <file>` reverts the *whole file*, not just the mutation —
stash or re-apply deliberately.

## 7. Start and monitor

```bash
cd /Users/nishantsingh/PlacedOn/placedon-law-backend

# start — dynamic pacing, self-scheduled
/loop

# state at any time
python3 scripts/verify.py | tail -1        # GO / NO-GO and the count
git log --oneline origin/main..HEAD        # unpushed iterations
python3 scripts/build_register.py --status # asked / answered
cat .claude/plans/loop-runbook.md          # this file

# stop
/loop stop
```

## 8. The one line

> The loop can finish the plumbing. It cannot clear Gate 1, and Gate 1 is the product. Six clauses,
> one evening, one law student — that is the only work on this project that changes a number.
