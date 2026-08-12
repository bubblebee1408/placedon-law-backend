# The Sonnet Era plan, checked

Written 2026-08-12, reviewing `PLACEDON_SONNET_ERA_PLAN.pdf`.

Its headline call — **switch the default to Sonnet** — is right, and it is now in
`backend/budget.py`. One of its details is right and better than what we had, and is now in
`checker/distress.py`. Its Phase 1 would have made this product actively worse for the person it
matters most to, and is not implemented. Details below, in order of how much damage each would do.

---

## 1. Phase 1 inverts the distress design, and the inversion is the harm

The plan's Prompt 3 says:

> *Route through trauma_wrapper AFTER lattice generates response. **Do NOT skip lattice — legal
> accuracy must remain.** Trauma wrapper softens delivery, not substance.*

This is a reasonable-sounding principle, and on this corpus it is exactly backwards. Measured —
`python3 scripts/bench_distress.py`, and every retrieval below is the measured top-3, not a guess:

| She types | Retrieval hands the model |
|---|---|
| *"Will they fire me if I complain about my manager?"* | s.13, **s.14**, s.5 — and **s.14 is _Punishment for false or malicious complaint_** |
| *"I was transferred after I reported him"* | s.13, **s.12**, s.11 — s.12 **permits transferring the aggrieved woman** |
| *"My manager touched me at the office party"* | s.3, **s.25**, s.20 — *Power to call for information and inspection of records* |
| *"I am scared to go to work"* | s.3, **s.1**, s.2 — s.1 is *Short title, extent and commencement* |

The plan proposes to prepend *"I understand this is a difficult situation. You are not alone"* to
these and soften the verbs.

**The substance is the harm.** A woman deciding whether to report her manager is handed the section
used against complainants; a woman describing retaliation is told the Act allows the thing being
done to her. Softening the delivery does not repair either. It makes a discouraging answer feel
caring, which is worse than delivering it plainly, because warmth is what makes it credible.

Note what fails here: nothing. Every guard passes. The citation is real, the quote is verbatim, the
section is on-topic. **A safety layer that checks the output against the retrieval cannot see this,
because the output is faithful to the retrieval — the retrieval answered a question nobody asked.**
That is why `distress.route()` runs *before* retrieval rather than wrapping after it.

The plan's own instinct — *"the system must be trauma-informed"* — is correct and is the reason the
route exists. The mistake is believing trauma-informed means a gentler voice. In the literature it
means **knowing when to stop being a system**: OlimpIA, HelloCass, AinoAid and Botler all escalate
to a human, early ([Wise 2025](https://asistdl.onlinelibrary.wiley.com/doi/10.1002/pra2.1349),
[arXiv 2402.17393](https://arxiv.org/pdf/2402.17393)).

## 2. The distress route was already built

The plan's status table says **❌ Not built — ethical obligation**. It shipped before this plan was
written: `checker/distress.py`, 30 tests, wired into `ask_engine.py` ahead of everything,
mutation-tested by `verify.py`, ₹0 per call because no model runs.

Worth flagging because the plan's Day 1 is spent rebuilding it, in the shape that causes §1.

## 3. A distress score of 0.0–1.0 is a confidence percentage wearing a different hat

Prompt 1 asks for `DistressResult(score: float 0.0-1.0)` with a 0.6 threshold.

This project has refused a confidence float seven times, latterly with evidence: `bench_safety.py`
showed an embedding score rating **two verbatim quotations of the statute** as more suspect than
four fabrications. A number that scores an exact quote as doubtful cannot be shown to a user.

A distress float is the same object with higher stakes. What is 0.55? It is a woman who gets the
compliance lecture because a hand-tuned regex weighting put her below a hand-picked cut-off. There
is no validation set that calibrates it and there will not be one, because building it means
labelling real distress.

The shipped design is ordinal and has no tuning surface: **one pattern match refers.** Recall over
precision, stated in the module and enforced by the `ROUTINE` set — a false positive costs an
employer one paragraph they did not need; a false negative is §1.

## 4. `[FLAGGED: A qualified advocate should review personally]`

We have no advocate. Printing this promises a review that no one will perform. The honest version
is what the route already says: *this is a computer program, not a person* — followed by contacts
who do have a duty to act.

## 5. `Confidence: 94% | Verified by: Adv. Sharma` and `XYZ vs. ABC (2024)`

Both are still in the mockups, and both were flagged in `LEGAL_AI_ARCHITECTURE_ANALYSIS.md` §1.1.
**We hold zero judgments.** There is no Adv. Sharma. A placeholder that is shaped like a citation
becomes a fabrication the moment it renders.

## 6. "Verify all 30 sections in 2 hours"

Four minutes a section, including reading the section. That is not review, it is initialling — and
a rubber-stamped `verified_by` is worse than a null one, because null abstains honestly while a
name asserts that a human checked. The name is the entire basis of the product's honesty.

The pack is **6 load-bearing clauses**, an evening's work, and `scripts/apply_verification.py`
already exists (the plan proposes building it as Prompt 4). Coverage 0% → 85% comes from those six.

## 7. Razorpay on Day 8, Streamlit on Day 4

- **₹999/month before Gate 1 buys a refusal.** `verified_by` is null on all 30 sections; the
  product abstains on everything by design. Charging for that is a refund queue.
- **`app.py` in Streamlit is a second frontend.** A Next.js app exists, is deployed, and fetches
  `/api/districts`. Two UIs means two places for the district list to drift — the exact bug fixed
  by deleting the second list. Mobile-first is right; it is CSS on the frontend we have.
- **The freemium gate needs an exemption written in code, not policy.** "3 free analyses, then
  upgrade" would, unqualified, count a woman asking whether she can be sacked for complaining.
  `verify.py` now asserts `cost_inr == 0.0` on the referral path so the rule survives the billing
  layer that has not been written yet.

---

## What the plan got right, and it is worth more than the rest

**The NCW helpline: 7827170170.** The route offered a portal, an email address and a statute — all
correct, all things you use *after* deciding what to do. It offered no way to talk to a person. The
plan noticed. It is now the **first** contact returned.

It was checked before it was written down
([MEA](https://www.mea.gov.in/helplineforwomenindistress),
[NCW](https://www.ncw.gov.in/contact-us/)) and its source is stored beside it, because an
unverified helpline is a worse failure than an unverified citation: a wrong citation is read by an
employer who may notice, and a wrong number is **dialled**, by someone in distress, at the moment
she has decided to ask for help. Nothing downstream catches that. `verify.py` now refuses any
contact without a re-checkable source.

Adding it surfaced a real bug: `ask_engine` was prepending the s.6 quote, so the helpline arrived
fourth. For a compliance answer the citation leads; **for a referral the citation is the
justification and the phone number is the answer.** Fixed.

**And the model call.** Sonnet is the right default for beta, for the reason the plan gives.
`DEFAULT_MODEL = "claude-sonnet-5"`.

One correction to its arithmetic: Sonnet is on introductory pricing ($2/$10 per 1M) until
**2026-08-31**, so today it is **₹1.94/answer**, not ₹2.91. `PRICING` still carries the list price
deliberately — a budget guard must only ever be wrong in the expensive direction, and encoding the
discount would leave the cap silently admitting calls it should refuse on 1 September.

---

## The sequence, corrected

| | Work | Blocked on | Status |
|---|---|---|---|
| 0 | Sonnet default | nothing | **done** |
| 1 | Helpline in the distress route | nothing | **done** |
| 2 | **Gate 1 — six clauses to a lawyer** | *a lawyer* | **the only thing that matters** |
| 3 | Conflict panel on the existing frontend, wording per `LEGAL_AI_ARCHITECTURE_ANALYSIS.md` §1.1 | nothing | queued |
| 4 | Re-run `bench_answers.py` on Sonnet vs Haiku; downgrade if coverage matches | 2 | queued |
| 5 | Pricing | 2 and 4 | not before 2 |

The plan's own one-sentence version is nearly right. The correction is one clause:

> Build the distress route — **it is built; the plan would have rebuilt it wrongly.** Verify the
> content. Ship the mobile UI **on the frontend that already exists.** Everything else is a
> distraction.
