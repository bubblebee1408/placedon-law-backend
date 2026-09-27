# 08: Self-critique: what would make each part worthless, and when to kill it

The founder asked for this plan to be doubted line by line. This is that pass, written by the
same author as 00–07. That is a limitation, so a reviewer who did not write it should repeat it.

## 1. Doubts about the plan as a whole

**"Is this a plan to build, or a plan to avoid building?"** Four of the seven requested parts are
declined or gated. The test is whether the declined parts were declined on evidence, not on
taste:

- NSE rests on its own terms. Those are [S], seen only in a search summary, because the fetch
  was blocked.
- Zauba rests on missing provenance plus unread terms, which are [OPEN].
- Judgment prediction rests on five reasons, two of them [V].

**Weakest point:** NSE and Zauba were not read first-hand. **Action:** the founder reads both
pages in a browser and pastes the clauses into `docs/research/`. If NSE's terms turn out to allow
display of corporate announcements, 02 §2 changes.

**"Does G1–G2 add value before anyone uses it?"** Replay and recall have no user until there are
served answers to replay. PLAN_17 M12 (pilot) is the first moment they matter.

- **The risk:** G1–G2 gets built for a customer who never arrives.
- **Mitigation:** both are small (S–M). Both give an engineering benefit now: G2.3's differential
  test consolidates three hand-rolled rollups.
- **Kill:** if M12 has not started within 6 months of G2 exiting, stop G3+ and put effort on
  H-001 instead.

**"Is the semiring worth it, or is it maths for its own sake?"** The honest test is whether
`dependents(x)` answers a question someone asks.

- It does: *"which answers relied on the notification that was just corrected?"* That is the
  question SD-003 and the RETRACTIONS history show this repo already had to answer by hand.
- **Kill:** if G2.4's revocation report on G.S.R. 880(E) finds no conclusion that the existing
  per-call lattice could not already list, the stored witnesses are overhead. Revert to per-call
  evaluation.

## 2. Doubts about specific claims

| Claim | Doubt | Status after doubting |
|---|---|---|
| "Evidence states form a semiring" (04 §2) | True for any chain, but only after an order is declared, and `provenance.STATES` is not one | Correct as stated; G0.5 makes the order a decision, not an assumption |
| "Append-only removes the need for DRed" (04 §4) | Holds for *structure*. But an entity-graph edge that was **wrong** (not withdrawn) still exists structurally, with ⊥ evidence | Correct: a ⊥ path yields a ⊥ alert, which `release` refuses. But the UI must hide or grey ⊥ alerts, or users see noise. Added to G3.1 as a rendering rule for the ux-designer |
| "227 audited edges per type" (04 §5) | That assumes zero errors are found. One error raises the n needed | Stated as the zero-error case; the audit reports counts regardless |
| "ILDC inputs are facts written by the deciding court" (04 §7) | Inference from the task design as summarised, not from reading the paper | Marked [I]; read ILDC in full before repeating it outside this repo |
| ACI bound formula (04 §9) | Transcribed from memory of Prop. 4.1 | Marked; the conclusion ("loose at our volumes") holds for any bound decaying as 1/(γT) |
| "No product ships recall of answers resting on withdrawn sources" (04 §2) | Checked only against Harvey and Spellbook's public surfaces | Marked [I], with its scope named |
| The Harvey BYOMCP fit (05 G4.5) | Harvey's partner requirements (OAuth 2.1, PKCE S256) are from a desk-research doc, not from building against it | Marked [I]; verify when M9 lands |
| "Sizes S/M/L" | Every estimate in this repo so far has been optimistic | Treat as ordering, not scheduling |

## 3. Things the plan might have missed

- **A lawyer's workflow may not include a terminal.** In-house teams live in Word and Outlook.
  The terminal (G4b) is the part most exposed to "nobody asked for this". **Kill:** if 3 pilot
  users are shown it and none uses it twice, drop it and keep the CLI for engineers only. The
  verb table stays either way; it is what keeps the three surfaces consistent.
- **The citator depends on counsel.** If counsel says the maintainer's CC-BY grant does not cover
  court text, G5 falls back to Indian Kanoon's paid API. The founder chose free-only, so G5 is
  then blocked, not merely delayed.
- **Entity resolution needs labelled true matches we do not have** (G6.1). If none can be built
  lawfully, G6 stops at exact-identifier linking, which is still useful for s.185/188.
- **The peer local session** has uncommitted work (the `RETRIEVAL_DEFECT` doc, and a red
  `parse_board_rules` suite). G0's exit gate includes landing it, which depends on that session.

## 4. What would falsify PLAN_19 specifically

In addition to PLAN_00's thesis falsifiers:

1. H-001's practitioner reads a replayed answer and a recall notice and says neither changes what
   they would do.
2. G3's alerts, once audited, turn out to be dominated by ⊥ or `SIGNAL` paths. That would mean
   the evidence the watch engine needs does not exist yet.
3. G0 shows the scope gate cannot reach 7/7 practitioner refusals on dev without also refusing
   held-law questions. That would mean a lexicon gate is the wrong mechanism, and a classifier
   (with its own labelled set) is needed before anything else.
