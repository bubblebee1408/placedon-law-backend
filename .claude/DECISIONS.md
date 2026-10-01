# Decisions

Each entry: what was decided, what it rests on, and the condition that would reverse it.

`.claude/INDEX.md` describes this file as holding "8 decisions". It has never existed in this
repository's history — the row was aspirational. It starts here, with one. The eight
model-and-platform decisions D1–D8 live in `docs/PLAN_22_MODEL_AND_PLATFORM_DECISIONS.md` and
are not duplicated here; this file is for decisions taken in the build loop.

---

## H0 — The refusal gate

**Decided 2026-09-30.** Mirrors `.claude/loops/DECISION_harvey_parity.md`, which selected the
trust-first sequence H0 → H6 and made H0 its first step. That document deferred this mirror
to "the laptop session when it starts H0"; this is it.

### The decision

Before any Harvey-parity feature is added, the engine must refuse what it cannot answer. On
the gold set's dev split it refused rightly on **5 of 17** and answered *"What is the capital
of France?"*. Adding web search, judgments and client repositories on top of a gate in that
state multiplies what a failing gate lets through.

### What was changed, and what was deliberately not

**A turn that read nothing is a refusal, not a partial answer.** Retrieval already computed
the signal — `evidence_pack.insufficient_evidence` with `abstain_reason: NOTHING_RETRIEVED` —
and the turn went out as `partial` regardless, which the gold set scored as an answer. One
rule in `checker/ask.py` now marks those `refused`. It moved 11 of the 12 failing rows.

**The refusal is a flag; the state stays `partial`.** `out_of_scope` means something
specific: a body `checker/scope.py` DECLARES, served in the register's own words. An
off-topic question names no such body, so there is no refusal text to serve and inventing one
would be writing law. That rule predates this work — it is in `checker/ask.py`'s docstring and
its Income-tax test — and it survives intact.

**One term of art was added, and two were refused.** `"open offer"` is the takeover code's own
vocabulary, absent from the whole held Act text, and it turns the SEBI practitioner row into
the register's *named* refusal rather than a generic one. `"asset test"` and `"payroll vendor"`
were **not** added: they are not competition-law or data-protection terms of art, and fitting
them would fit this split rather than name a body. A loose signal that wrongly refuses a HELD
question is the worse error `checker/ask_scope.py` exists to avoid. Those two rows refuse on
the no-evidence path instead — correctly, with a weaker reason than the register's.

### The result, and the row that did not move

Dev split: refused-rightly **5/17 → 16/17**; answered-correctly **9/13, unchanged**.

`off_tax_return` — *"When is my personal income tax return due?"* — still answers. Retrieval
reaches Companies Act s.212 (SFIO investigation) and s.2 (Definitions) on the words "return"
and "due", so there IS evidence and the no-evidence rule does not fire. Closing it needs
either a body the register does not declare, or a retrieval-precision rule that judges whether
a provision bears on a question. The second is real work and it is H1's. It is pinned as a
named test in both directions, so it cannot grow and cannot close silently.

### The held-out split, run once, reported as it is

`--split test`, code hash `fe3521e788ec`, 17 rows. The ledger shows this is the **first and
only** held-out run ever recorded, so there is no before-number: whether these figures are an
improvement cannot be stated, only what they are.

    answered-correctly  4/6
    refused-rightly     10/11

Two things in it matter more than the counts.

**One answer row was wrongly REFUSED** — `held_s149_stay`, *"How long must a director have
stayed in India to count as resident?"* The report's words: *"refused a question it should
have been able to answer."* That is a question about HELD law, and refusing one is the worse
error — the error `checker/ask_scope.py`'s docstring is built around not making, and the
tripwire named in this decision's own reversal condition. The new no-evidence rule caused it:
retrieval reached nothing for that phrasing, so the rule fired.

It is recorded and **not fixed**. The held-out split is never to be tuned against, and
diagnosing that row against its own text is exactly the tuning the split exists to prevent.
It is evidence about the rule, to be acted on through the dev split or a new labelled row.

**One refusal row answered with provisions** — `off_bank_interest`, reaching s.63, s.125 and
s.186. The same shape as `off_tax_return` on dev: retrieval finds Companies Act text for a
question the Act does not govern. Two independent rows, on two splits, pointing at retrieval
precision rather than at the refusal rule. That is the case for H1 owning it.

### Reversal condition

`DECISION_harvey_parity.md` set it: **if H0 cannot bring the dev refusal rows to 17/17 without
losing answer rows, stop widening — no H1b/H2 until it does.** It reached 16/17. The remaining
row is a retrieval-precision defect, not a refusal defect, and H1's source framework is where
it belongs. If H1 ships without closing it, that reversal condition binds and the sequence
stops there.

Reverse this decision if the refusal rule starts refusing questions about held law: that is
the worse error, and the nine named answer rows are the tripwire.
