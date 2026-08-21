# Next phase — retire the risks, not add features

Written 2026-08-21, after Week 1 and the Week 2.1 acquisition attempt.

## The honest position

Weeks 1–2 built genuinely good verification machinery: a section index at 97.9% with 17 mappings
read by hand, an amendment parser at 98.7%, enforced evidence states, instrument-qualified
references, a tamper-evident audit log. 11 suites, 314 checks.

And yet **two facts should govern everything that happens next**:

1. **The entire corpus rests on one artifact that has never been independently checked.**
   `INDIACODE_CA2013_PDF` is the sole source. It is hashed, re-fetched, byte-identical, authentic —
   and single. If that PDF is defective, every downstream output is faithfully wrong, and nothing
   in the test suite would notice. `VERIFIED` in this repo means *verified against that artifact*,
   which is a much weaker claim than it reads as.

2. **No lawyer has ever used any of this.** Zero contact with the target user. Every product
   assumption is untested.

We have been building depth on an unvalidated foundation. The next phase must retire those risks
before adding capability, because everything built on top inherits them.

## What this week actually revealed, strategically

The stated moat is **statutory currency** — being right about what the law says *today*. This week
we could not acquire one subordinate instrument, because four India Code endpoints return 403 and
the file host is down.

That is not just an operational annoyance. **The moat and the bottleneck are the same thing.** A
product whose differentiator is currency, built on a supply chain that fails for a week at a time,
has a strategic problem that no amount of parser quality fixes. This needs an answer before it is
sold to anyone as "always current":

- either a supply strategy that does not depend on one publisher's uptime,
- or an explicit, honest lag with abstention when the corpus is stale.

The second is defensible and cheap. The first is expensive. Pick deliberately; do not drift into
claiming the first while operating the second.

## The four risks, ranked by what they would cost if wrong

| # | Risk | Current state | Cost if wrong |
|---|---|---|---|
| R1 | The corpus is single-sourced and unverified | `UNVERIFIED` | Everything downstream is wrong, silently |
| R2 | Point-in-time reconstruction has never been checked externally | `UNVERIFIED` | The core technical claim is unsupported |
| R3 | The SS scanner over-fires; recall never measured | 18/18 false positives once | Product is unusable; trust lost on first use |
| R4 | No lawyer has used it; the market model is still CS-based | Untested | Building the wrong thing well |

Note R1 and R2 are both *verification* risks and both are gated on **acquiring a second source** —
not on writing code. That is the critical path.

## P0 — Independent verification of the corpus and reconstruction

**This is the highest-value work available and it is blocked on an acquisition, not on engineering.**

The retraction in `docs/RETRACTIONS.md` happened because a current consolidation was used as
pre-amendment ground truth. The fix has always been the same: obtain an **independent rendering**
of the same law and compare.

Two candidate sources, both permitted:

1. **The Act as enacted (2013 Gazette).** With it, reconstruction becomes testable for the first
   time: reconstruct s.X as of 2013-08-30 and compare against the as-enacted print. Disagreement
   localises the bug; agreement is the first genuine evidence the engine works.
2. **Indian Kanoon**, under its attribution terms. Free-tier access needs an application — human,
   and worth starting now because lead time is unknown.

**Gate:** reconstruction of ≥20 amended sections agrees with an independent source, or the
disagreements are understood and documented. Until then no accuracy claim may be made externally.

**Opportunistic:** while retrieving the Rules, also grab the as-enacted 2013 Act if it is visible.
Two downloads, one browser session. This single artifact unblocks R2.

## P1 — Finish Week 2.1 and ingest the Rules

Blocked on the human download. Everything downstream is ready: identity classification refuses
amendments and consolidated reprints, the audit log is tamper-evident, the namespace keeps Act and
Rules apart.

After `VERIFIED_PRINCIPAL`, in order, stopping for review between each:
storage → hash re-check → text extraction → extraction-quality report → rule↔section linking from
the rules' own text.

**Do not** infer a rule's enabling section from its number.

## P2 — Measure the scanner honestly

The scanner has never had its recall measured. Precision was catastrophic once (18/18 false
positives on real documents) and was fixed by document-type gating, but "fixed" is not "measured".

- 30–50 documents, ≥10 with known defects, from permitted sources (ICSI specimens, public
  listed-company disclosures).
- **Labels frozen before evaluation.** Any label written after seeing output is circular.
- Report precision *and* recall. A scanner that misses defects silently is worse than one that
  over-fires, because over-firing is visible.

**Gate:** precision and recall both stated with confidence intervals, on frozen labels.

## P3 — Put it in front of a lawyer

Not a survey. One corporate lawyer, real documents, watching them work. The question is not "would
you use this" but "what did you do immediately before and after this task".

Cheapest useful version: run the scanner over documents they already reviewed, and compare against
what they actually flagged. That measures value without needing a product.

## P4 — Rebuild the market model for the lawyer segment

`R-011`. The existing model is built on Company Secretaries, a segment explicitly abandoned. It
should not be cited anywhere until rebuilt. Low urgency, high embarrassment risk if quoted.

## What I would do differently, in hindsight

The section index, amendment parser, and provenance layer are sound work. But three weeks in, the
system has never been checked against anything outside itself, and the one attempt to get an
independent source has been blocked for a week. **The second source should have been acquired
before the first thousand lines were written**, because it is what converts "our tests pass" into
"we are right".

Sequencing principle for the next phase: **acquire evidence before building on it.**

## Human-gated, on the critical path

These cannot be done by the agent and everything else waits on them:

1. Download the principal Rules (in flight) — `docs/ACQUISITION_HANDOFF_board_rules_2014.md`.
2. Download the as-enacted 2013 Act — unblocks R2, the largest technical risk.
3. Apply for Indian Kanoon free-tier access — unknown lead time, start now.
4. Find one corporate lawyer willing to be watched working for an hour.
