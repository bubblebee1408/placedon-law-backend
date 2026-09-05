# H-001: getting one Company Secretary to review the matrix

This is the highest-value open task in the project and the only one that has
been blocked on a person from the start. The benchmark can tell you the checker
is internally consistent. It cannot tell you whether the obligations, the
evidence fields, the refusals, or the wording match how the work is actually
done. Only a practitioner can, and one is enough to be worth more than another
feature.

Everything you need is built. What remains is sending one message.

## Who — one, not a panel

A **practising Company Secretary**, not a lawyer, and here is the uncomfortable
reason the project has been avoiding: `PRODUCT_SCOPE.md` says "lawyer, not CS",
yet every well-evidenced workflow in `WORKFLOW_BACKLOG_INDIA.md` is CS work, and
the one company-side interview named CS unprompted (`R-011`, open). This review
is also the cheapest way to settle that contradiction. Pick a CS.

Prefer someone in **small or independent practice** over a large firm — that is
the buyer the product is aimed at, and their frustrations are the ones it must
answer.

Where to find one, in rough order of ease:

- Anyone you already know who is a CS, or one degree away. A warm introduction
  outperforms everything below.
- A local ICSI chapter. Chapters run study groups and events; a member doing
  small-company secretarial work is exactly the profile.
- LinkedIn: "Company Secretary" + a city, filtered to independent practice or
  small firms.

You need **one who says yes**. Ask three.

## The message

Short, honest, and asks for judgement rather than endorsement. Send it as-is.

> Hi [name] — I'm building a compliance-checking tool for the Companies Act and
> I'd value twenty minutes of your judgement before I build any further. It is
> not finished and I'm not selling anything; I want to know where it's wrong.
>
> It takes a company's basic facts and produces a compliance matrix — one row
> per obligation, each saying whether the duty applies, whether it looks met, or
> what's missing. I'd like to show you seven rows and have you tell me which ones a
> real practitioner would call wrong, which refusal is useful and which is just
> annoying, and what a real matter needs that isn't there.
>
> There's a one-page version you can look at first:
> https://claude.ai/code/artifact/6b731f1a-ee40-46eb-a5e9-797994c07eaf . Happy
> to do this on a call or in person, whenever suits.

The one-page version is `docs/validation_kit.html`, live at
**https://claude.ai/code/artifact/6b731f1a-ee40-46eb-a5e9-797994c07eaf** — republished
2026-09-05 and current with the engine (it had drifted: it described the s.2(85)
refusal as blocked on G.S.R. 700(E), which stopped being true when that instrument was
attested). The URL is stable across republishes, so this link can be sent as-is.

**Check before sending:** the artifact is private by default. Open it and share it from
the page's share menu, or the recipient will get nothing. It leads with the
ICSI-specimen staleness finding, which is checkable in a minute and establishes
the problem is real before you ask for anything.

## What to show, in order

1. **The ICSI specimen finding first.** Their own professional body's specimen
   AGM notice still carries auditor-ratification language omitted 07-05-2018 and
   "service tax" subsumed 01-07-2017. A CS can verify this from memory. It earns
   the next twenty minutes.
2. **One worked matrix**, run live: `python3 scripts/serve_matrix.py`, a real
   private company, all four row states on screen including the s.2(85) refusal.
3. **The six rows, one at a time.** For each, one question: *would a practitioner
   call this right or wrong?*

## What to capture — and how

Do not capture "they liked it". Capture per-row verdicts and specific
corrections. The tool is built for this:

    python3 scripts/record_interview.py

It has a field for each of the six rows, for the refusal reaction, for what
obligations are missing, and for the one row they would sanity-check first. It
also captures the harder Tier-1 signals — what they pay for today, whether they
have ever been asked a past-dated question, whether they redo work when a rule
changes. Those test the claims the business rests on, and a practitioner's
answer to "what do you pay for" is worth more than any opinion of the UI.

The single most valuable output is a **row they say is wrong, with the reason**.
A corrected row is worth more than a confirmed one, and the whole point of
asking is to find the ones we got wrong.

## The two safety findings to watch for

Two answers matter more than the rest and are flagged in the tool:

- **`trust_without_checking = y`** — if a CS says they would act on a green row
  without checking the source, that is a *risk*, not a success. The product must
  make verification easy, not replace it.
- **`small_refusal_reaction = broken`** — if the s.2(85) refusal reads as the
  tool being broken rather than as rigour, the refusal UX has failed and needs
  rework before anyone relies on it.

## What this review is allowed to change

Everything downstream. If the CS says an obligation is missing, it goes on the
backlog ahead of what is there. If they say a refusal is annoying, the refusal
UX changes. If they say the whole framing is wrong for how a CS works, that is
the most valuable answer of all and it reorders the roadmap.

Do not defend the design in the room. The goal is not to be told you are right.
It is to find out where the system's model of legal work is wrong, while it is
still cheap to change.
