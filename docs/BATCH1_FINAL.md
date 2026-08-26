# Batch 1 — final report

**Closed:** 26 Aug 2026 · reviewer-01 · 10 items, all decided

## Result

| Status | n |
|---|---|
| **EXACT** | **1** |
| PARTIAL | 7 |
| ABSTAIN | 2 |
| CONFLICT | 0 |

Batch 1 validated the witness-matching, commencement-provenance and fail-closed
review workflow on ten omission cases. One reconstruction is exact; seven remain
partial; two remain unresolved.

## The one EXACT

**121-m1** — s.121(2), Companies Act 2013

| Field | Value |
|---|---|
| Omitted words | *within the time as specified, under section 403* |
| Amending clause | Act 1 of 2018, s.31 — "Amendment of section 121" |
| Witness | indiankanoon.org/doc/9573987 · clause `sha256:217f2583…` |
| Commencement | **S.O. 1833(E)**, Gazette Extraordinary No. 1646, 7 May 2018, item 7 |
| Notification hash | `sha256:a84eb58f…` |

Full chain: amending clause → subsection identity → exact wording → source hash
→ commencement instrument → effective date.

## Why 161-m2 is not EXACT

The wording and clause identity are sound: Act 1 of 2018, s.51 omits
*"In the case of a public company,"* from s.161(4), and those words are absent
from the current consolidation.

**But S.O. 1833(E) does not list section 51.** It appoints 7 May 2018 for
sections 2, 8, 13, 18-19, 21, 23, 30-31, 33, 39-40, 46, 49, 52, 54-58, 61-62,
80, 83 and 86-89. India Code's footnote nonetheless gives s.161's amendment that
date.

The effective date is therefore **not inferred**. `commencement_status` is
UNKNOWN until a notification naming section 51 is found.

This disagreement was invisible while the date stood alone, and surfacing it is
what the commencement field is for.

## What the strict definition cost, and what it bought

Adopting Option A moved 161-m2 from EXACT to PARTIAL. The batch's headline fell
from 2 exact to 1. That is the correct direction: the item that survived is
provable end to end, and the one that did not was resting on a date no
instrument supported.

## Verification performed

- immutable review record: 10 entries
- every recorded clause hash re-verified against a fresh extraction
- notification hash re-verified against the retrieved bitstream
- exact set membership: `['121-m1']`
- non-EXACT records marked promotable: none
- full test suite green; manifest regenerated and verified

## Defect fixed during this step

`parse_sections` counted section 1 as commenced. "Sub-Section (2) of Section 1"
is the power the notification is made *under*, not a provision it brings into
force. Counting it overstated what the instrument did.

## Open, deliberately not started

- **Which notification commenced amending-Act s.51.** Search the remaining
  commencement notifications for section 51 itself, not for the date
  2018-05-07 and not for principal-Act section 161. If none names it, 161-m2
  stays PARTIAL with `commencement_status = UNKNOWN`.
- **Batch 2.** Not begun.
