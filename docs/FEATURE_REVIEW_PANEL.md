# Placedon — Feature Review

## An evidence-backed compliance engine for Indian corporate law

**Reviewed 11 September 2026 · three-role panel · India market**

---

## How to read this document

Three roles reviewed the same ten features independently and did not see each
other's work:

- **The Advocate** — the strongest honest case for each feature, from the buyer's side
- **The Reality Checker** — what is *actually* in the code, read line by line, tests run
- **The Devil's Advocate** — the arguments most likely to kill the product

They disagreed. Section 5 is where they converge, and it is the only section that
carries a recommendation. Where a number below is checked against the running
code it is marked **verified**; where it is a judgement it is marked as one.

**One correction the review itself produced.** The Reality Checker found that
`docs/FEATURES.md` described F1 as "specced, not built" when the API route in
question had shipped a day earlier. That has been fixed. It is recorded here
because a review that produces no corrections has not happened.

**A second correction.** The Reality Checker read a mid-flight state and reported
4 of 15 obligation rows refusing. Verified against the running engine at the time
of writing: **2 of 15**. G.S.R. 880(E) was attested on 10 September, and s.2(85)
now answers.

---

## 1. The ten features, in plain language

## F1 · Document Currency Check
**In one line:** is the rule this document relies on still the rule?

You open a board resolution signed in June 2024. It treats the company as a
"small company" because its capital is under ₹4 crore. That limit changed on
1 December 2025 — it is now ₹10 crore. The document was right when it was signed
and is wrong when you read it, and nothing about the document tells you that.

This reads the document, notices, and names the exact Gazette notification that
moved the figure. It works on the date the document was made, not today's date.

## F2 · Compliance Matrix
**In one line:** what does the law actually require of this company?

You type in basic facts — private or public, incorporation date, capital,
turnover, how many directors. You get back a list of duties the Companies Act
puts on that company, and for each one: does it apply, does it look met, or what
is missing.

The list comes from the law, not from paperwork. A company that has uploaded
nothing still gets the full list — and the rows with nothing behind them are
usually the ones that matter.

## F3 · Evidence Pack
**In one line:** the same list, in a form you can hand to someone else.

A dated, stamped document for a buyer's counsel during a transaction. It carries
an explicit list of **what could not be checked**. That list is the part that
earns trust: a report that admits its own gaps is one a lawyer can rely on for
the parts it does claim.

## F4 · Company Event Log
**In one line:** what changed, and when did we find out?

A timeline with two dates on everything: when it took effect, and when we learned
it. That sounds fussy until you notice a lawyer asks two different questions —
*"what do we now know about March"* and *"what could we have known in March"* —
and only the second one matters when someone is asking whether you were negligent.

## F5 · Law-change Monitor
**In one line:** tell me when a rule I rely on changes.

A notification appears in the Gazette → these duties move → these companies are
affected. Not a calendar reminder. A dated, sourced alert that names the
instrument.

## F6 · Point-in-Time Answer
**In one line:** what did the law say back then?

A transaction happened in March 2019 and someone is now asking whether it was
compliant. The right question is what the law said **in 2019** — not what it says
today. Almost nothing on the market answers the first question; most answer the
second and present it as the first.

## F7 · Staleness Audit
**In one line:** what are we relying on that nobody is watching?

An internal check, and arguably a feature in its own right. For every rule the
system uses to reach an answer: do we hold it, has a person read it, and would we
notice if it changed?

## F8 · Bulk Document Review
**In one line:** fifty contracts in, one table out.

Upload many documents, get a spreadsheet of key terms — termination dates,
governing law, change-of-control clauses. When it cannot read a page it **leaves
the cell empty and says which page**, rather than filling it with a guess.

## F9 · Grounded Research Assistant
**In one line:** ask a question, get a cited answer or an honest "I don't know".

Not a chatbot. It answers only from law it holds, with the section and date
attached, and refuses when it cannot. The refusal is deliberate: a wrong legal
answer costs more than no answer.

## F10 · Controlled Drafting
**In one line:** it writes the document and shows where every number came from.

Every line is labelled by origin — boilerplate, a fact you supplied, a quote from
the law, a date it calculated, or a suggestion. **If any part is a suggestion or
missing, the draft cannot be approved** until a human sources it. So nobody
accidentally signs something built on a guess.

---

## 2. Architecture — how each feature is built

The engine is a **lattice, not a pipeline**. The usual design —
`parse → embed → retrieve → generate → check` — fails because nothing downstream
of a bad retrieval can detect a bad retrieval. Here, the decision layer never
touches a model.

**The evidence for that choice is measured, not stylistic.** On a 32,436
article-version corpus of French tax law, static retrieval returned the
date-applicable version of a provision **0% of the time** across 209 questions,
while confidently citing real but inapplicable text (arXiv:2608.09393). And
stronger-reasoning models are *worse* at temporal applicability, not better —
old-version accuracy below 0.25 against 0.70–0.84 current (arXiv:2608.14610).
**A better base model widens this gap rather than closing it.**

### The four layers

| Layer | Model? | What it does |
|---|---|---|
| **Decision** | none | applicability, dates, thresholds, obligations |
| **Currency** | none | is the legal basis still in force on the date asked about? |
| **Retrieval** | encoder only | find the governing provision |
| **Narration** | frontier model, four refusals before any call | phrase results already verified |

**Nine of twenty internal roles use a model. Five use a frontier model. Zero
decide whether a law applies.**

### Per-feature architecture

**F1 · Document Currency Check.** `document_extract.ground()` requires the
extractor to quote the span it read; the span must exist in the document and the
parsed value must follow from it. Then `POST /v1/document-check` compares the
obligation's legal basis at the *document's* date against the *reading* date. The
comparison is on the **governing instrument**, not the currency status — a
distinction that cost a real bug when acquiring an instrument caused the check to
stop firing.

**F2 · Compliance Matrix.** `obligations.py` (1,460 lines) holds 15 rows. Each
decider is deterministic. A row refuses when the delegated rule behind it is
unheld, and names the acquisition reference.

**F3 · Evidence Pack.** `diligence_pack.py` renders the matrix with a provenance
block — corpus hash, code commit, law-as-of date — so a reader can reproduce it.

**F4 · Company Event Log.** Content-addressed events, bitemporal (`at` vs
`known_at`), with one invariant enforced in the constructor: **an event with no
verifier cannot be a verified fact.**

**F5 · Law-change Monitor.** `currency.affected_by()` is the reverse index: a
Gazette fragment → the obligations it moves → the companies affected.

**F6 · Point-in-Time Answer.** `as_of.py` plus dated threshold records with
explicit `effective_from`/`effective_to`. Instruments are acquired one at a time
through a two-human-check route.

**F7 · Staleness Audit.** For every external instrument: acquisition state, and
whether a successor would have anywhere to be recorded.

**F8 · Bulk Document Review.** Not built. Would need a tiered OCR pipeline —
cheap OCR first pass, frontier VLM for stamped/Devanagari pages, human QA on low
confidence — with **OCR confidence as another admission gate**, so an unreadable
page yields an empty cell naming the page rather than a guess.

**F9 · Grounded Assistant.** `reasoning.py` is the model contract: seven named
violations, each with a stub that commits it. `shadow.py` scores a model without
serving it. `session.py` holds the document in memory with no path to disk.

**F10 · Controlled Drafting.** Typed provenance slots; `approve()` raises on any
slot that is a model suggestion or unknown.

---

## 3. The panel

### 3.1 The Advocate

*Which Indian buyer feels this, in what moment, and what does it cost them today.*

**F5 · Law-change Monitor — the strongest budget fit of the ten.** A Big Four
compliance practice or a practising Company Secretary with a 10–30 company book,
the week a Gazette instrument lands. "Regulatory monitoring" is already a priced
service line inside Big Four retainers. A PCS buys this as **career insurance**,
not efficiency — a wrong small-company exemption on an MGT-8 certificate is ICSI
disciplinary exposure, not embarrassment.

**F3 · Evidence Pack — the highest willingness to pay.** Buy-side diligence
counsel, mid-negotiation. Today: associates manually pull MCA21 filings, charge
registers, s.164(2) disqualification checks — 40–100+ hours per deal at firm
rates. The sharper Indian cost is **the deal re-trading**: the buyer's team finds
what the seller's team missed, days before signing. And the "what could not be
verified" list is the part diligence counsel actually wants, because they would
otherwise reconstruct it themselves to cover their own liability.

**F2 · Compliance Matrix — the most fundable, because it exists.** In-house CS
preparing the quarterly board compliance certificate, or a consulting team
onboarding an acquired subsidiary. A duty that attached but was not tracked
surfaces as an adverse remark in Form MR-3, a ROC show-cause, or a published
s.454 adjudication order — **public, and attributable to the CS who signed.**

**F1 · Document Currency Check — the lowest sales friction.** One lawyer, no
procurement committee, value visible on the document already open. Rides an
existing budget line: per-seat legal research spend, the same category as SCC
Online.

**Cautioned against overselling: F8.** Best unit economics on paper, but the
repo's own OCR research says it cannot yet meet legal-grade accuracy on real
Indian scanned documents. Selling it now is the one place this *"we refuse when
we cannot verify"* product would itself be over-promising.

### 3.2 The Reality Checker

*Read line by line. Tests run. Verified against the running engine.*

**Verified:** all suites green. **13 of 15** obligation rows answer for a typical
Indian private company; 2 refuse (s.177 Rule 6 held-but-unread, s.203
chain-traced-but-unconfirmed).

**Six routes live**, all pure functions — and the file asserts its own
model-freedom by parsing its own imports.

**Point-in-time benchmark: 1.00, zero wrong answers**, against a
"latest figure" baseline that serves a 2024 date the ₹10 crore figure which only
took effect in December 2025. The docstring states the limit itself: one
two-instrument chain — *"the mechanism works on what we hold"*, not a coverage
claim.

**The finding that matters most:** no model call has ever fired against a live
API key in this system's history. `reasoning.py` and `shadow.py` are a
well-tested contract and harness **for a model that has never met them.** Calling
F9's spine "built" is fair; calling it close to a usable assistant is not.

**Also flagged:** "monitor" implies automation, but acquisition is manual by
design, and SEBI's RSS is the only machine-readable feed in Indian law. F5 as a
*product* needs a human in the loop indefinitely — not just until launch.

### 3.3 The Devil's Advocate

*The arguments most likely to kill it.*

**The flagship story has a detail the pitch will not want said aloud.**
Placedon's own engine served the superseded ₹4 crore threshold as CURRENT for
nine months. F7 exists *because of that incident*. So the canonical proof-point
for "look how stale everyone else is" is a story where **the company telling it
had the identical defect, for the identical duration** — and it was caught by an
internal self-test, not a customer, not a lawyer, not a loss event.

That cuts both ways and both are bad: it proves the failure mode is real and easy
to fall into, **and it proves the failure mode produced zero observed harm** even
inside the company whose business model is catching it. Nine months, and the cost
was nothing.

**Refusal at 11pm.** 2 of 15 rows refusing is one thing; 8 of 9 declared bodies
of law holding zero instruments is another. A partner with a signing deadline
does not admire the refusal — they open the bare Act, or text the retained CS,
and get an answer in five minutes. The second time, the tool is demoted from
*"how I work"* to *"what I check on Tuesdays."* **Trust-from-refusal is a
threshold effect, and nobody knows which side of it this sits on**, because no
lawyer has used it under time pressure.

**The crack in the thesis.** You cannot claim "we verify against the Gazette, not
consolidations" as the moat and then hold SEBI LODR — the second body most
in-house counsel live in — *as a consolidation with no amendment history*. That is
not a coverage gap; it sits in the second row of the scope register.

**The free competitor is not another SaaS.** It is the retained CS or firm, who
already builds "is this current" into the relationship because that is the entire
value of the retainer. And the CS whose exposure this addresses has a **structural
disincentive to champion a tool that automates their own value proposition.**

**Cut:** F8 entirely, not "phase 3". F6 as a standalone pitch (fold it into F2/F3
as an internal guarantee — with three instruments held, arbitrary point-in-time
questions are a parlour trick that survives one question and not two). F10 until
F9 has a wired model.

---

## 4. Where they disagreed, and how it resolved

**On F1.** Advocate ranked it third and called it "specced, not built". The
Reality Checker read the code and found the backend live and tested — **only the
Word UI is missing.** The Advocate was arguing from a stale document. *Resolved in
the Reality Checker's favour, and the document was corrected.*

**On refusal.** The Advocate called the "what could not be verified" list the
feature diligence counsel actually wants. The Devil's Advocate called it a
demotion to Tuesday-only usage. **Both are right, and they are not talking about
the same buyer.** Diligence counsel wants the gap list because they carry
liability for missing it and have time to act on it. A partner at 11pm wants an
answer. *Resolved: the gap list sells to a reviewer, not to someone under a
deadline — which decides the launch buyer.*

**On the staleness hook.** The Advocate treated the ₹4 crore case as the closing
argument. The Devil's Advocate pointed out the same bug ran inside Placedon for
nine months with zero consequence. *Resolved in the Devil's Advocate's favour:
the hook demonstrates the mechanism, it does not yet demonstrate the cost.*

---

## 5. The panel's single result

### 5.1 What all three accept

1. **The mechanism is real and measured.** 1.00 against a baseline that gets a
   2024 date wrong. 13 of 15 rows answering. Suites green. This is not vapour.
2. **The harm is not yet demonstrated.** Four websites being wrong is evidence of
   a mechanism, not of a cost. Nobody has been shown to have lost anything.
3. **No model has ever run.** The safety architecture is real and untested
   against a live model.
4. **Scope is one body of nine.** The register makes that honest and also makes
   it legible to a buyer in ten seconds.

### 5.2 Which feature is the real pain point

**F5, the Law-change Monitor — but only for one buyer.**

Not the in-house team: they believe their retained CS covers it, and mostly the
CS does. The pain concentrates on **the advisor with a book of clients** — a PCS
with 10–30 companies, or a consulting compliance practice. When a threshold
moves, they must identify every affected client before someone else does, and
being late is a liability and reputational event, not an inefficiency.

That buyer already has a budget line called regulatory monitoring. And the ₹4
crore case is that buyer's own nightmare told back to them.

### 5.3 Which features are low-importance but still required

**F7 (Staleness Audit) and F4 (Event Log).** Neither sells. Nobody has a budget
line for either. Both are required anyway:

- **F7** is the answer to *"how do I know you are not the fourth vendor still
  saying ₹4 crore?"* It is not a feature, it is the proof the other features are
  safe to believe. Cutting it removes the only evidence the product is what it
  claims.
- **F4** is retention. Nobody buys an event log; people renew because of one.

Ship both. Price neither.

### 5.4 The sellable bundle

**F3 + F2 + F5, sold as one thing: a compliance position you can hand to someone
who will check it.**

- **F2** produces the position — 13 rows answering today
- **F3** makes it handable — dated, cited, with the gaps named
- **F5** keeps it true — and is the feature the buyer already budgets for

F2 and F3 are built. F5's engine is built and needs delivery. **The whole bundle
is closer to shippable than any single feature the panel ranked first.**

**F1 is the wedge, not the bundle.** Lowest friction, one lawyer, no committee —
but it needs the Word add-in, and it opens a door rather than closing a sale.

### 5.5 What the panel recommends cutting

| Cut | Why | Dissent |
|---|---|---|
| **F8 Bulk Review** | OCR cannot meet legal-grade accuracy on real Indian scanned documents. Every quarter on the roadmap is a quarter a buyer asks "when" and gets a non-answer | Advocate notes best unit economics — but agrees it cannot be executed credibly today |
| **F6 as a standalone pitch** | Three instruments held. Survives one demo question, not two. Fold into F2/F3 as *"every figure here is point-in-time correct"* | None. All three agree the machinery stays and the pitch goes |
| **F10 until F9 runs** | Drafting liability built on an assistant that has never met a model | None |

---

## 6. What would change the panel's mind

Stated as falsifiers, because a recommendation that cannot be wrong is not one.

**One documented instance of actual harm.** Not "four sites are wrong" — a real
Indian company or professional who filed something incorrect and faced a
consequence because they trusted a stale secondary source. Without it, the hook
demonstrates a mechanism with no established cost. **This is the single highest-value
thing to go and find.**

**Usage under time pressure, n≥5.** Not demo enthusiasm — week three, under a
filing deadline. Do they still open it after the second refusal?

**A second body of law fully held**, with obligations wired — proving the
acquisition pipeline generalises rather than being bespoke tooling built once.
SEBI LODR held *as a consolidation* does not count, and the panel was explicit
that it currently reads as a crack in the thesis rather than progress against it.

**A price from someone outside the founder's network.** Demand is n=1. Indian deal
sizes could not be sourced.

---

## 7. The honest summary

This is a rigorous engine with a real measured result, a scope register that
makes its own gaps legible, and an unusual willingness to find and publish its own
defects — five in shipped code during the review period, two of them in work
produced the same week.

**It is also a product nobody outside the repository has used, solving a problem
nobody has yet been shown to have lost money to, for a buyer whose budget has not
been confirmed.**

The engineering risk is low and falling. The market risk is the whole risk, and no
further building reduces it.

*The model may propose. The system must verify. The reviewer decides.*
