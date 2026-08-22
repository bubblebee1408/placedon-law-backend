# Practitioner interview kit — v2, built to be refuted

One session, ~45 minutes. Same structure for all five. Print it. Fill it in live.

This version tests the specific claims in `CLAIMS_TO_TEST.md`, which came from **simulated**
personas. Nothing in them is evidence. The point of the session is to find out which are real.

**Target — five *distinct* people:** practising CS · CS-firm employee · corporate lawyer · CA doing
company compliance · junior doing the research.

## Rules

- **Baseline before demo.** Once they've seen the answer the baseline is worthless.
- **Ask about the last time, not about generally.** "How often do you…" gets self-image. "Tell me
  about the last time…" gets an event you can probe.
- **Numbers, not adjectives.** "Time-consuming" is not data. "Two hours, last Thursday" is.
- **A yes with no date, document or name is a no.** Write it down as a no.
- **Do not correct them during the task.** You promised to tell them at the end. Mean it.
- **Let silence run.** The useful sentence comes after the pause.

---

## STAGE 1 — what they actually do

Ask before anything is shown. Six questions, all about events that already happened.

**1.** Walk me through the last board resolution you prepared. What did you open first?

> Sources named: ____________________  *(B1: is it 4+?)*

**2.** Tell me about the last time you had to redo a document because a rule had changed.

> Happened? y/n/? ____  When: ________  What did it cost: ________  *(T4)*
> If they can't recall one — **that is a finding.** Write "none recalled."

**3.** Has anyone ever asked you what the law was on a past date?

> Last instance: ________________  What did you do: ________________  *(B2)*
> How long did it take: ______

**4.** Do you pay anyone — a person or a service — to tell you when rules change, or to do
historical research?

> Pays for alerts: y/n  ₹______  *(T2)*
> Pays for historical research: y/n  ₹______  *(T3 — the claim I most expect to be wrong)*

**5.** What do you currently pay for legal research tools, and who signs it off?

> Tool: __________  ₹______/yr  Approver: __________  *(T1, P1)*

**6.** How many filings or sets of minutes did you personally do last quarter?

> Count: ______  *(T5, T6)*

**7.** Who drafts this in your office — you or someone junior? Why?

> *(B3 — if they say "I do it myself because juniors miss things", that is the delegation claim)*

---

## STAGE 2 — the baseline task

Hand them this. **Start the timer.**

> Financial year end: **31 March 2026**
> Previous AGM: **10 May 2025**
> *What is the last date for the next AGM?*

**Start ____:____  Answered ____:____  Elapsed ______ sec**

Their answer: ____________________

| Observe | |
|---|---|
| Opened any source | ☐ MCA ☐ ICSI ☐ bare Act ☐ commercial DB ☐ own template ☐ memory only |
| Checked the **six-month** limb | ☐ |
| Checked the **fifteen-month** limb | ☐ |
| Answered **10 Aug 2026** (fifteen-month binds — correct) | ☐ |
| Answered **30 Sep 2026** (six-month only — missed it) | ☐ |
| Raised a Registrar extension | ☐ |

> **Do not correct them.** Whether experienced professionals miss the fifteen-month limb is the
> single most informative observation available here.

Then: **"Same question, but for financial year 2018–19."**

> What they did: ____________________  Time: ______  *(B2 — the claim that would most change the plan)*
> Could not answer ☐   Answered from memory ☐   Opened a source ☐

---

## STAGE 3 — the demo

```bash
python3 scripts/slice_s96.py
```

Show it. Say nothing about what it is for.

1. Which part of this is useful?
2. Which part is noise?
3. What would you still check yourself?
4. Would you trust this date — **without opening the section?**
5. It refuses to approve the draft because the venue and business are missing. Helpful or annoying?

| Observe | |
|---|---|
| Read the provenance panel | ☐ |
| **Opened / asked for the source text** | ☐ *(B4)* |
| Noticed the two limbs | ☐ |
| Reaction to the blocked approval | helpful ☐ annoying ☐ no reaction ☐ |

> **If they'd trust it without checking — that is a SAFETY finding, not a win.** Their exact words:
> ____________________

---

## STAGE 4 — commitment, not opinion

A yes here only counts with a date, a document, or a name.

1. Would you run this on a real matter — **which one, and when?**
   > Date named: __________  ☐ vague
2. Can you send me an anonymised document to test?
   > ☐ yes, sent  ☐ yes, promised  ☐ no
3. Who decides whether your firm buys something like this?
   > Name/role: __________  ☐ wouldn't say
4. What would make you stop using it?

**Commitment:** none ☐ / vague yes ☐ / named a date ☐ / gave a document ☐ / named the buyer ☐

---

## Close

Tell them: **10 Aug 2026**, the fifteen-month limb binds. You promised.

Then the most valuable question in the session:

> **"Would that have mattered in real work?"**

If they got it wrong, their reaction to being wrong is worth more than everything they said before.

**Verbatim quote worth keeping:** ____________________

---

## After the session

```bash
python3 scripts/record_interview.py --new
python3 scripts/record_interview.py --summary
```

Record blanks as blanks. **Unobserved is not "no."**
