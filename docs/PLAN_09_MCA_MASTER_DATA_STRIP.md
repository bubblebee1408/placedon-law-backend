# PLAN 09 — The MCA Master Data Strip: analysis, simulation, and what it changed

**Date:** 2026-09-12 · **Status:** engine built and green; live data not wired (by design)
**Code:** `checker/mca_snapshot.py`, `checker/mca_reconcile.py`, `checker/party_resolution.py`, `checker/buyer_sim.py`
**Run it:** `PYTHONPATH=$PWD python3 checker/buyer_sim.py`

---

## 0. The short version

The proposed Master Data Strip is a good feature built on a wrong premise. The premise is
that the MCA register tells you what is true right now. It does not. It tells you what has
been **filed**, and the Companies Act itself grants the company a window between the event
and the filing — up to 60 days for a charge created, and up to **300 days** for a charge
discharged (s.77(1) first proviso, s.82(1) proviso, both quoted from our own corpus).

So a bar reading `Active Charges: 2` beside a green pill reading `MCA Reconciled (0
Conflicts)` and a badge reading `Synced 14m ago` is precise about the wrong quantity. The
fetch is fourteen minutes old. The knowledge is up to ten months old, in the direction that
flatters the seller.

Three defects, and the middle one is the expensive one:

| # | Spec cell | Defect | Severity |
|---|---|---|---|
| 1 | `Warranties Breached: Attach CHG-4 NOC` | A register cannot establish a breach. s.82(1) permits the satisfaction to be 300 days late; the warranty may be qualified by a disclosure letter not in the document set; it may speak as at a different date. | Loses the account |
| 2 | `Signatory Invalid: Rectify before EGM` | **Wrong law.** DIN deactivation for KYC default arises under the Directors Rules. The office becomes vacant only on the grounds in **s.167(1)**, a closed list that does not reach the status of a DIN. `mca_reconcile._test()` re-reads s.167 from our corpus and fails if the word `deactivat` ever appears in it. | Wrong, checkably |
| 3 | `IF post_money_shares × nominal > authorised` | Ignores class. s.4(1)(e)(i) registers capital together with *"the division thereof into shares of a fixed amount"* — headroom is per class, and a company with ₹1 Cr of preference headroom has none of it available to an equity allotment. | Wrong answers on real MOAs |

And one defect that is not a cell but the whole bar: **8 of the 8 cells that render a field
the Act leaves blind render it as settled.** That number is measured, not asserted — see §4.

---

## 1. The engineer's ten stages

Written as the order I would actually build it, with the gate that closes each stage.

| # | Stage | Gate that closes it |
|---|---|---|
| 1 | **Decide what the register is.** Not a truth source — a filing ledger with a statutory lag. | The lag is expressed in code as a per-field window with a *direction*, not as a `last_synced` timestamp. |
| 2 | **Source every window from the Act we hold.** No blog, no memory. | Each `Window` carries a verbatim fragment; `verify_against_corpus()` fails the build if the fragment leaves the corpus. 8/8 windows verified. |
| 3 | **Name the fields we cannot bound.** s.39(4) prescribes the return of allotment by rule and states no period; DIR-3 KYC is a rule too. We hold neither. | `paid_up_capital` and `din_status` return `UNBOUNDED_BLIND` and name the acquisition. They never return a width. |
| 4 | **Make absence un-renderable as denial.** | `may_assert_absence("charges")` returns `False` with the s.77 window as the reason — and cites the window that moves the value *up*, not the wider one that moves it down. |
| 5 | **Write the reconciliation rules as conflicts.** | `Finding.__post_init__` raises `Overclaim` on `breach / invalid / void / violat / illegal / unlawful / non-compliant`, in the headline **and** the question. A future rule cannot reintroduce the word by writing careful prose. |
| 6 | **Refuse rather than compute on a missing input.** | Aggregate authorised capital → `REFUSED` citing s.4(1)(e)(i). An unregistered class → `REFUSED`, not assumed. |
| 7 | **Never return AGREES from a floor.** | A fitting allotment against an unbounded-blind issued figure returns `UNRESOLVABLE`. It becomes `AGREES` only once that blindness is bounded — which is exactly what acquiring the Allotment Rules would buy. |
| 8 | **Grade the evidence honestly.** | `Snapshot.evidence_grade` is `SECONDARY`, permanently. A SHA-256 proves our custody, not MCA's statement. The primary artefact is an MCA-issued signed document, and `scripts/verify_document.py` already checks that chain. |
| 9 | **Simulate the buyer before building the UI.** | `buyer_sim.py`: ten questions, four outcomes, `OVERCLAIMED == 0` as the gate. |
| 10 | **Wire live data last, behind a contract.** | `corporate_data.LicensedAggregatorProvider` still refuses. There is no scraping path and there will not be one (CLAUDE.md). |

Stages 1–9 cost nothing and are done. Stage 10 costs a commercial agreement, and on a
₹2,000 budget it is out of reach — which is why it is last and not first.

---

## 2. The same feature, from a corporate lawyer's desk

An Indian M&A or company-secretarial lawyer does not want a dashboard. They want the three
minutes before signing to stop being the scariest three minutes.

**What they actually do today.** Pull the master data and the index of charges from the
portal. Eyeball them against the SPA's capital clause and the encumbrance warranty. Ask the
CS whether anything is pending. Sign.

**Where that goes wrong, in this market specifically.**

- **The satisfaction lag.** Charges discharged years ago still sit on the index because
  CHG-4 was never filed. MCA has run repeated settlement schemes over exactly this. A tool
  that shouts "breach" at every stale entry will be muted inside a week.
- **The disclosure letter.** The encumbrance warranty in the SPA is almost never absolute;
  it is qualified by a schedule in a different file. Reading the agreement alone and
  concluding anything is reading half the contract.
- **Authorised capital by class.** The MOA's capital clause splits it. Aggregate headroom
  is a number that looks like an answer and is not one.
- **DIN vs office.** Every Indian company lawyer knows a deactivated DIN means the person
  cannot sign an e-form. Telling them it invalidates a board resolution marks the tool as
  written by someone who has not done the work.

**What they would pay for.** Not the data — that is free on the portal, and Q9 in the
simulation says so out loud. What is not free is a **dated record of what was checked, what
the Act left blind on that date, and what the tool refused to conclude.** That artefact has
value in 2029, when somebody asks what was known at signing.

---

## 3. Four questioning models

Adversarial lenses applied to every cell before it ships. Each has one standing question.

| Lens | Standing question | What it killed here |
|---|---|---|
| **The Register Sceptic** | *If this number is wrong, in which direction, and how far back does the error reach?* | The green `0 Conflicts` pill. Answer: up to 60 days upward, 300 days downward. |
| **The Deal Lawyer** | *Name a completely innocent fact pattern that produces this alert.* | "Warranties Breached." Three innocent patterns exist; all three are now in the finding text. |
| **The Litigator** | *Read this screen back to me in 2029 under cross-examination.* | `evidence_grade = SECONDARY`. A hash of an aggregator payload is not the registry's statement. |
| **The Procurement Officer** | *What does this cost per company per deal, and who pays when it is wrong?* | The live-sync architecture. WebSockets pushing sub-second updates of a quantity that changes monthly, against per-CIN aggregator pricing. HTTP with a cached snapshot is both cheaper and more auditable. |

---

## 4. The simulation

`checker/buyer_sim.py` — ten questions an Indian buyer asks, each wired to the code that
would have to answer it. Outcomes: `ANSWERED`, `REFUSED_CORRECTLY`, `GAP`, `OVERCLAIMED`.
Only `OVERCLAIMED` must be zero; a `GAP` is a roadmap item.

```
  id  buyer              outcome            states a   hides
                                            conclusion blindness
  ------------------------------------------------------------
  Q1  M&A partner        REFUSED_CORRECTLY  no         YES
  Q2  General counsel    REFUSED_CORRECTLY  YES        YES
  Q3  M&A partner        ANSWERED           YES        YES
  Q4  General counsel    ANSWERED           no         YES
  Q5  In-house legal     ANSWERED           no         -
  Q6  M&A partner        ANSWERED           no         -
  Q7  General counsel    ANSWERED           no         YES
  Q8  In-house legal     REFUSED_CORRECTLY  no         YES
  Q9  M&A partner        ANSWERED           no         YES
  Q10 General counsel    ANSWERED           no         YES

  {'REFUSED_CORRECTLY': 3, 'ANSWERED': 7}
  spec cells stating a legal conclusion:        2/10
  spec cells rendering a blind field as settled: 8/8
```

**The two comparison columns are measured, not opinions.** The spec's own cell text is passed
through `Finding`'s constructor — the same guard that governs our output — and through
`spec_hides_blindness()`, which asks whether a cell rendering a blind field names the window.
A cell reading `Active Charges: 0 — a floor; s.77 allows 60 days to register` passes. The
guard measures the disclosure, not the topic.

**Q10 is the one that matters.** *"Your bar said zero conflicts, we signed, a charge from
twenty days before signing has surfaced. Who is liable?"* The answer is structural: the probe
sweeps every combination of document statement and register contents and asserts the charge
rule reaches `{CONFLICTS, DOCUMENT_SILENT, REGISTRY_SILENT, UNRESOLVABLE}` and **never**
`AGREES`. There is no input that produces an all-clear, so there is no all-clear to have
relied on. That is a property of the code, not a promise in a contract — and if someone
later adds an `AGREES` path, this test fails.

**Q6 was the honest gap, and it is now closed.** A buy-side SPA names four CINs — target,
seller, acquirer, holdco — and the spec pins one "Active CIN" to the bar. The correction in
`checker/party_resolution.py` is that *pinning a CIN is the wrong question*: *a CIN is never
a party, a role is*, and each rule needs a different role. Capital headroom runs against the
**issuer**. The encumbrance warranty runs against the **target**. DIN reliance runs against
the **executing entity**. On the same four-party document that is two different companies
and one refusal — because nothing in it says who is executing, and the rule names the missing
role rather than reaching for whichever CIN came first.

Three further refusals fall out of the same file:

- **A role with no span is `UNGROUNDED`.** `document_extract` already refuses a field the
  document does not support; identity gets the same discipline.
- **Two evidenced targets is `AMBIGUOUS`**, never first-wins.
- **A scanned CIN is reported, never repaired.** `U722OOKA2O21PTC145892` — zeros read as the
  letter O — is recognised as scanner damage, the correct candidate is *named*, and the raw
  value is returned unusable. Repairing it would be a lookup against a different company.

---

## 5. What the simulation changed

It was run **before** any UI existed, and it changed the engine four times:

1. **`may_assert_absence` cited the wrong proviso.** The first version picked the widest
   window (s.82, 300 days). But absence asks "could there be *more*", which is the *upward*
   direction — s.77, 60 days. The assertion passed while the reasoning was wrong; it now
   selects only windows whose direction is `FLOOR` or `EITHER`. A real-sounding citation for
   the wrong direction is worse than no citation.
2. **The conclusion guard moved into the constructor.** It began as a test. A test catches
   the rules that exist; a constructor catches the rule someone writes next year.
3. **The guard grew a second half.** It caught 2 of 10 spec cells. The far more common
   defect — rendering a blind field as settled — is invisible to a word filter, so
   `spec_hides_blindness()` was added. It caught 8 of 8.
4. **Capital headroom stopped returning `AGREES`.** Against an unbounded-blind issued
   figure, "it fits" is a claim we cannot make. This is the rule refusing to be usefully
   dishonest, and it converts an acquisition task into a measurable upgrade.
5. **Then it produced a module.** Q6 was left as a `GAP` rather than papered over, and
   `party_resolution.py` was written to answer it — 23 checks, and the harness moved Q6 to
   `ANSWERED` on its own. That is the loop this harness exists for: the simulation names the
   hole, the hole gets code, the harness proves it rather than a note in a document claiming
   it was fixed.

---

## 6. Consequences for the architecture and the RAG system

**The boundary, stated once: a registry figure never enters a prompt as retrieved context.**

Master data is structured, dated fact. Retrieval is semantic and undated. A number that
arrives via cosine similarity is a number you cannot attach a blind window to, cannot cite a
form for, and cannot refuse on. So the lattice keeps three lanes apart:

| Lane | Input | Mechanism | May a model touch it? |
|---|---|---|---|
| **Law** | the Act, rules, notifications | `legal_retrieval` / `structural_retrieve`, point-in-time | Yes — to find and quote |
| **Registry fact** | `Snapshot` | typed field + `Assessment`; no embedding, no index | **No.** It is passed as a value, with its blindness attached |
| **Document fact** | the draft | `document_extract` — span-grounded, one ungrounded field poisons the record | Yes — to extract a span, never to conclude |
| **Reconciliation** | the three above | `mca_reconcile` — pure functions | **No.** Deterministic or it is not evidence |

Three concrete changes this forces:

- **No `mca_*` collection in the vector store.** If a registry value is ever embedded, the
  blindness is lost at the moment of retrieval, and every guarantee in §1 evaporates.
- **The narration layer already covers this.** `reasoning.py` has seven violations including
  `FIGURE_INVENTED` and `FACT_WITHOUT_SPAN`, and narration drops *whole*. A registry figure
  quoted into prose without its field must be caught there, not reviewed for.
- **The routing consequence.** Reconciliation is free — it is arithmetic. The only paid model
  call in this feature is extracting the document's own figures and clause references, which
  `router.py` sends to the HIGH tier because a mis-read capital clause is consequential.
  A strip that refreshes on a WebSocket would have been a per-deal recurring cost for a
  quantity that changes monthly.

---

## 7. What the initial prototype session can actually perform

**Can, now, with no key and no contract:**

- Assess any master-data field for blindness, with the window quoted from the Act and the
  direction of error stated (`mca_snapshot.assess`).
- Run the three reconciliation rules — capital headroom per class, encumbrance warranty,
  DIN reliance — and produce findings that cannot contain a legal conclusion.
- Resolve which company each rule runs against on a multi-party deal document, and refuse
  when the document does not say (`party_resolution.subjects`).
- Check a CIN's structure, flag scanner damage without repairing it, and catch a CIN whose
  incorporation year post-dates the document.
- Run the ten-question buyer simulation end to end and show `OVERCLAIMED: 0`, no `GAP`.
- Demonstrate all of it inside Word through the add-in (`addin/`), against a real document
  with a real document date.

**Cannot, and should not pretend to:**

| Blocked on | What it blocks | Cost to unblock |
|---|---|---|
| A contracted MCA aggregator | Live snapshots. The provider still refuses; there is no scraping path. | A commercial agreement — out of reach at ₹2,000 |
| Prospectus and Allotment Rules 2014, r.12 | A bound on paid-up capital; turns Q7/Q4 from `UNRESOLVABLE` into `AGREES` | Acquisition + human attestation |
| Directors Rules 2014, r.12A | Any statement about DIN deactivation beyond "the register says so" | Acquisition + human attestation |
| ~20 real documents | Extraction accuracy on Indian capital clauses; the whole HIGH-tier claim | Legwork, not money |

**Q6 is done** — `party_resolution.py`, the difference between "works on a board
resolution" and "works on a deal". Of what is left, the two delegated rules come next,
because each converts a refusal into an answer and that is a demonstration a buyer
understands. The aggregator comes last: until a lawyer has reacted to the refusals, live
data is an expensive way to be wrong faster.

---

## 8. Provenance of every legal statement in this document

| Claim | Section | Verified |
|---|---|---|
| Charge registration — 30 days | s.77(1) | `mca_snapshot.verify_against_corpus()` |
| Charge registration — outer 60 days (post-2019) | s.77(1) first proviso (b) | same |
| Satisfaction — 30 days | s.82(1) | same |
| Satisfaction — outer 300 days | s.82(1) proviso | same |
| Alteration of capital — 30 days | s.64(1) | same |
| Directors — 30 days | s.170(2) | same |
| Financial statements — 30 days from AGM | s.137(1) | same |
| Annual return — 60 days from AGM | s.92(4) | same |
| Premium does not consume capital | s.52(1) | read from corpus while drafting |
| Capital is registered as divided | s.4(1)(e)(i) | read from corpus while drafting |
| Vacation of office is a closed list not reaching DIN status | s.167(1) | `mca_reconcile._test()`, asserts `deactivat` absent |
| Return of allotment states no period in the Act | s.39(4) | read from corpus; the period is in an unheld rule |
