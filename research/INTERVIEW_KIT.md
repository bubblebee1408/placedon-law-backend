# Practitioner interview kit

One session, ~45 minutes, same structure for all five. Print this. Fill it in live.

**Target sample — five *distinct* professionals, deliberately mixed:**

| | Who |
|---|---|
| P1 | Practising company secretary |
| P2 | CS firm or in-house compliance team |
| P3 | Corporate lawyer |
| P4 | Chartered accountant doing company compliance |
| P5 | Junior/mid-level doing the document research |

## Rules for the interviewer

- **Do not demo first.** The baseline is worthless once they have seen the answer.
- **Do not explain what the tool is meant to prove.** You will get agreement, not evidence.
- **Do not ask "do you like it".** Ask what they did, and what they will do.
- **Let silence run.** The useful sentence usually comes after the pause.
- **Record behaviour, not intentions.** "I always check MCA" is a claim; watching them open MCA is data.
- If they ask what the right answer is — say you will tell them at the end, and mean it.

---

## STAGE 1 — baseline task (before any demo)

Hand them this, and start timing.

> Financial year end: **31 March 2026**
> Previous AGM: **10 May 2025**
> *What is the last date for the next AGM?*

**Start time ____:____   Answer given at ____:____   Elapsed ______ sec**

Their answer: ________________________________

| Observe — tick what actually happened, not what they say they do | |
|---|---|
| Opened a source at all | ☐ |
| Which: MCA ☐  ICSI ☐  bare Act ☐  commercial DB ☐  own notes/template ☐  memory only ☐ |
| Checked the **six-month** limb | ☐ |
| Checked the **fifteen-month** limb | ☐ |
| Arrived at **10 Aug 2026** (fifteen-month binds) | ☐ |
| Arrived at **30 Sep 2026** (six-month only) | ☐ |
| Mentioned a Registrar extension | ☐ |
| Asked a clarifying question first | ☐ |

> The fifteen-month limb binds here. If they answered 30 Sep 2026, **do not correct them yet** —
> note it and carry on. Whether experienced professionals miss it is the single most informative
> observation in this study.

Then ask, without leading:

1. How did you work that out?
2. Would you check that anywhere before sending it to a client?
3. How would you answer the same question for financial year **2018–19**?
4. Have you ever found guidance that turned out to be outdated or superseded?
   → If yes: **what happened?** (get the story, not a yes)
5. What goes in the client file as evidence for this date?

---

## STAGE 2 — the demo

```bash
python3 scripts/slice_s96.py
```

Show it. Say nothing about what it is for. Let them read.

Then:

1. Which part of this is useful?
2. Which part is noise?
3. What would you still check yourself?
4. Would you trust this date? *(then:)* Would you trust it **without opening the section**?
5. It refuses to approve the draft because the venue and business are missing. Helpful, or annoying?
6. Where would this sit in how you actually work?

| Observe | |
|---|---|
| Did they scroll to / read the provenance panel | ☐ |
| Did they open or ask for the source text | ☐ |
| Did they notice the two limbs | ☐ |
| Did they notice the "derived, not in the Act" line | ☐ |
| Did they react to the blocked approval — positively ☐ / negatively ☐ / not at all ☐ |

> **If they say they would trust it without checking — that is a safety finding, not a success.**
> Write down their exact words.

---

## STAGE 3 — commitment (not opinion)

1. How often do you hit a question where the version of the law matters?
2. What do you do when two sources disagree?
3. Would you run this on a real matter this month? *(a date, not a maybe)*
4. Can we test it on an anonymised document of yours?
5. Who decides whether your firm pays for something like this?
6. What would make you stop using it?

**Commitment obtained:** none ☐ / will test ☐ / gave a document ☐ / named a date ☐ / pilot discussion ☐

---

## Close

Tell them the answer (10 Aug 2026, fifteen-month limb) and why. You promised.
Ask: *"Would that have mattered in real work?"* — their reaction to being wrong, if they were, is
worth more than anything they said earlier.

**Verbatim quote worth keeping:**
_______________________________________________
