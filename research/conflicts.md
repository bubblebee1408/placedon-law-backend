# Conflicts and evidence corrections

## CORRECTION-01 — the "product-market-fit signal" is n=1

`EVIDENCE_stale_rule_in_the_wild.md` (19 Aug 2026) describes a practising professional publicly
stating a superseded rule, and calls it *"the closest thing to a product-market-fit signal this
project has found."*

**The observation is sound. The framing is not.** Structuring the surrounding dataset shows:

| | |
|---|---|
| Comments in the set | 42 |
| Distinct authors | **16** |
| Written by the single most prolific author | **26 (62%)** |
| Comments carrying a date claim | 10 |
| Distinct authors making those date claims | **1** |
| Is that author the subject of the evidence file? | **Yes** |

So every date claim in the corpus — including the superseded-rule example — comes from **one
person**, who also wrote nearly two-thirds of the dataset. The apparent breadth of "42 practitioner
comments" is largely one commenter posting repeatedly across 40 different posts.

**What still holds:** a professional did publish superseded compliance guidance, in public, dated,
retrieved from a live source. That is a real observed failure and a legitimate reason to build a
date-and-amendment verification capability.

**What does not hold:** that this demonstrates a widespread inability to track amendments, or
anything about product-market fit. n=1 is an anecdote worth investigating, not a signal worth
planning around.

**Action:** the hypothesis is unchanged; its evidential weight is downgraded. It is now an
interview question, not a finding. Ask five practitioners whether they have acted on guidance that
turned out to be superseded — and count the people who say yes, not the comments.

## CONFLICT-02 — dataset topicality

The set was collected as *practitioner* evidence for a **Companies Act** product, but 15 of 42
comments concern income tax and 7 concern GST. 24 touch Companies Act matters, from 12 distinct
authors.

Not a defect in the data — taxguru.in covers all three — but it means the effective Companies Act
sample is smaller than the headline count, and the commenters may be tax practitioners rather than
company secretaries. **Role is not stated in any record and was not inferred.**

## Open — legal claims requiring official verification

7 comments assert a duty or a date a reader might rely on (`claims.csv`,
`claim_type=LEGAL_CLAIM`). Every one is marked `REQUIRES_OFFICIAL_VERIFICATION`. None has been
checked against MCA or the Act, and none may be used as a statement of law.

This is the same failure mode the product targets: compliance guidance circulating without a
verifiable date or source. It would be a poor irony to import it as fact.
