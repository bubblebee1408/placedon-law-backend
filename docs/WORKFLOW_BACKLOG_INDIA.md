# Ranked workflow backlog — India, Companies Act 2013

Written 1 Sep 2026. Companion to `docs/FEATURE_PLAN_INDIA.md`, which ranks **features**. This
document ranks **workflows** — the units of work a practitioner actually starts, finishes and bills.
It is the demand-side view of the same repository; where a workflow maps onto a feature already
ranked in the feature plan, this document cites `F1`–`F14` rather than restating it.

No web search was available (session budget 200/200 exhausted). No new primary research was
conducted for this document. Every claim about frequency, market, pricing or user desire is marked
**ASSUMED** or **UNVERIFIED** unless it points at a specific artefact in this repo.

---

## 0. Read this before reading the ranking

### 0.1 The evidence we actually hold about users

| | |
|---|---:|
| Practitioner interviews conducted | **4** |
| Of those, corporate lawyers | **0** (property/family, general practice, and one senior generalist) |
| Of those, Company Secretaries | **0** |
| Of those, company-side decision-makers | 1 (Manoj Murarka, Manishankar Oil — Hindi ASR transcript, noisy) |
| Practitioner comments analysed | 42, from **16 distinct authors**; 26 (62%) by one author |
| Comments touching Companies Act matters | 24, from 12 authors |
| Comments carrying a date claim | 10, from **1 author** — the same person |
| Interviews recording a **workflow frequency** | **0** |
| Interviews recording a **task duration** | **0** |
| Interviews recording **willingness to pay** | **0** |

Sources: `research/CHECKPOINT.md`, `research/conflicts.md`, `research/comment_analysis.md`,
`research/claims.csv`, `~/PlacedOn/Placedon-law-business-plan/docs/INTERVIEWS.md`.

`research/INTERVIEWS.md` **does not exist** in this repo — the interview record lives only in the
business-plan repo. `~/PlacedOn/Placedon-law-business-plan/docs/primary-data.md` **does not exist**
either; it was named in the brief and was not found. Both absences are recorded here so nobody
searches for them again.

> **The consequence, stated once and applying to every row below: we have zero evidenced frequency
> for any workflow in this document.** Not one practitioner has told us how often they do any of
> these things. Every "frequency" cell is therefore either ASSUMED from statute (the Act itself
> fixes how often an AGM happens) or ASSUMED from enforcement data (how often the ROC penalises a
> defect, which is not how often a practitioner does the work).

### 0.2 What our four interviews *do* support

Three findings recur across all four and are the only user-side statements strong enough to build on:

1. **Documents are physical.** Four independent confirmations, including the company side
   (*"सब physical रहते हैं"*). Any workflow assuming a clean digital pipeline is contradicted by
   every interview we have. Note that `corpus/testdocs/MANIFEST.md` says every document we hold is
   text-extractable — **our corpus is the opposite of what our interviews describe.** OCR quality is
   untested. This is a live risk on every document-in workflow below.
2. **The trusted use of AI is finding and sourcing, never composing.** One quantification offered
   (Lawyer 1's "75/25"). Nobody asked for drafting; nobody asked for a chatbot.
3. **Every stated pain was verification** — of a quotation, of an amount, of a counterparty.

And one finding that cuts against our declared scope: the company decision-maker, asked unprompted
who would use this most, said **"CA है, company secretary"**. `docs/PRODUCT_SCOPE.md` (locked 20 Aug)
says the primary customer is a **corporate lawyer** and explicitly *"not a product aimed primarily at
Company Secretaries"*.

> **Unresolved segment conflict, flagged and not resolved here.** Every workflow in this backlog with
> strong in-repo evidence — minutes, AGM notices, SS-1/SS-2, annual filings, MGT-8 — is Company
> Secretary work. Our declared buyer is a lawyer. Our enforcement corpus penalises the *certifying*
> professional, which is a CS function. `R-011` (rebuild the market model for the lawyer segment) is
> **open**. This backlog ranks by workflow value, not by segment, and where a workflow is
> CS-shaped it says so.

### 0.3 How the ranking works, and one correction to the brief

The brief asks for `(value to user) / (evidence we can produce today)`. Read literally that ratio
**rewards workflows we cannot evidence**, which is backwards. `docs/FEATURE_PLAN_INDIA.md` uses the
same phrase and plainly means the opposite. I read it as the feature plan does:

> **rank = value to the practitioner, gated by the evidence we can put in front of a sceptical
> practitioner this week, from artefacts already in this repository.**

A workflow with world-changing value and nothing to show scores low. That is the point.

**Value** = how much of a real, recurring, consequence-bearing task the workflow removes.
**Evidence today** = HIGH (working code + real documents + a demo we can run), MEDIUM (machinery
exists, no surface or no real documents), LOW (documented only), NONE.

**Build cost:** small ≤ 1 week solo · medium 1–3 weeks · large > 1 month. Costs assume no new
third-party dependency (`CLAUDE.md`) and no new corpus acquisition unless stated.

### 0.4 One enforcement fact that should make us uncomfortable

`checker/ss/RULES.md`: Secretarial Standards orders are **~4%** of published adjudication orders.
**Filing defaults under s.92/s.137 dominate at 16.2%** — four times the volume. Our deepest
enforcement research sits on the smaller class, and `docs/FEATURE_PLAN_INDIA.md` §4 declines to
build a "generic deadline calendar" (correctly, for false-positive reasons). W6 below is the
attempt to hold both facts at once.

---

## 1. The ranking

| # | Workflow | Value | Evidence today | Cost | Verdict |
|---|---|---|---|---|---|
| **W1** | AGM cycle: when is it due, and does the notice hold up | High | **HIGH** | Medium | **BUILD FIRST** |
| **W2** | "Is my template still the law?" — precedent staleness audit | High | **HIGH** (unusual: we hold the demo) | Medium | **BUILD FIRST** |
| **W3** | Board-meeting year in review (s.173 count and gap) | High | **HIGH** (code) / LOW (documents) | Small | **BUILD FIRST** |
| W4 | Minutes / SS-1 / SS-2 defect scan with exposure arithmetic | Very high | **MIXED** — rules HIGH, scanner LOW | Large | Build 4th, rework not extend |
| W5 | "What did the law say on date D?" | High (moat) | MEDIUM-HIGH (machinery) / NONE (demand) | Medium | Build as a row expansion, not a product |
| W6 | Annual filing chain: AGM → AOC-4 → MGT-7/7A → ADT-1 | High | MEDIUM | Medium | Blocked on rules we do not hold |
| W7 | Company classification / which regime applies | Gating | **BLOCKED** | Small once unblocked | Human action `S-002` |
| W8 | Related-party transaction approval route (s.188 / r.15) | High | MEDIUM | Medium | After W7 |
| W9 | New-incorporation first-90-days pack | Medium | MEDIUM | Small | Cheap filler, low pull |
| W10 | Charge registration (s.77 / CHG-1) | High per instance | **NONE** | Medium | Corpus gap |
| W11 | Director appointment / DIN / DIR-3 KYC | Medium | LOW | Medium | Corpus gap |
| W12 | Secretarial audit (MR-3, s.204) | High | LOW | Large | Wrong customer size |
| W13 | Company-law due diligence on a target | Very high | NONE | Large | No document mass |
| W14 | Counterparty verification (PAN / GST / bank name) | Unknown | **N/A** | Medium | Our only unprompted user ask — and out of scope |

---

## 2. The workflows in detail

Each entry gives: the workflow in the practitioner's words · the trigger · frequency and whether it
is EVIDENCED or ASSUMED · sections and rules touched · verifiable today vs blocked · deterministic
checks available · how it can be wrong and what it must refuse · build cost.

---

### W1 — "The AGM's coming up. When's the last date, and is this notice going to hold?"

**In their words.** *"Client's FY ended 31 March. When do I have to have the AGM by — and can you
look at this notice before it goes out?"* Two questions the practitioner treats as one job because
they arrive together.

**Trigger.** Financial-year close; the board fixing a date; a client forwarding a draft notice for
sign-off; a Registrar extension application being considered.

**Frequency.** Once per company per financial year for the deadline; once per notice for the review.
A practice with 20 client companies therefore runs it ~20 times between April and September, heavily
clustered. **ASSUMED — statutory, not observed.** The Act fixes the annual rhythm (s.96(1)); nothing
in our research says how many companies a practitioner carries. The interview kit
(`research/INTERVIEW_KIT.md` Stage 2) uses the AGM deadline as its baseline task, so **we chose this
workflow; no practitioner named it.** That is the honest provenance.

**Sections and rules.** s.96(1) and its first proviso (six-month limb, fifteen-month limb,
nine-month first-AGM limb, Registrar extension) · s.2(41) financial year · s.101(1) twenty-one clear
days · s.102 explanatory statement for special business, s.102(5) penalty · s.136 financial
statements circulated with the notice · s.146 auditor attendance · SS-2 clauses 1.2.10, 2.1, 4.2 ·
s.99 (fine, criminal, court-imposed — **not** a s.454 penalty).

**Verifiable today.**
- The deadline itself: `checker/s96_slice.py` is **built and passing**. It carries `Act 1 of 2018`
  s.26 as the substitution witness, `S.O. 2422(E)` as the commencement instrument with its list item
  quoted, both text hashes, fidelity EXACT on both sides of 13 June 2018, and it **names the binding
  limb**. `checker/agm.py` verifies the interval phrase verbatim against the cited provision before
  deriving anything. `scripts/slice_s96.py` runs it — this is the only end-to-end demo we own.
- The notice: **nine real AGM notices from five listed issuers, 2024–2026**, in
  `corpus/testdocs/agm_notices/`, plus ICSI's specimen notice. Per `corpus/testdocs/MANIFEST.md`,
  every one carries an s.102 explanatory statement, a signature block with a named CS and ACS
  number, a notice date and a meeting date. T3.1, T3.3, T3.5, T3.7 are all testable against real
  filed text **today**.

**Blocked.**
- **Registrar extension.** `docs/COMPLIANCE_MECHANICS.md` §4 item 1 is unresolved: whether an
  extension displaces the fifteen-month limb or only the six-month one. No ROC order or MCA
  clarification located. The card carries it in `UNRESOLVED_NOTES` and must keep doing so.
- **OPC annual-return date** (§4 item 2) has no "should have been held" anchor at all.
- **Whole-section reconstruction remains UNVERIFIED** against any independent source
  (`docs/RETRACTIONS.md`). The s.96 span is one of the ten genuine unclosed India Code spans
  (SD-003) and could not be reconstructed before 13 June 2018 until Act 1 of 2018 s.26 supplied the
  boundary. Pre-2018 answers rest on that single witness.
- **T3.2 (attendance slip + proxy form) will over-fire** on every modern notice: most 2024–26
  notices are VC/OAVM, where proxies do not apply. The check must be conditional on meeting mode.
  Unbuilt.
- Our nine notices are all **listed large/mid-cap** issuers. A small private company's AGM notice —
  the actual target document — is **not in the corpus**. We are validating on the wrong size of
  company and should say so to any tester.

**Deterministic checks available.** Deadline with named binding limb (`checker/agm.py` three limbs) ·
twenty-one clear days with both endpoints excluded, and the ≥95% *written* consent carve-out, oral
consent expressly insufficient (T3.5, Wurknet) · **special business genuinely classified as special,
with an explanatory statement** (T3.1, s.102(5) — **the highest per-officer figure in the entire
68-order corpus at ₹50,000 per director**, and the highest-value single check we own) · notice signed
by a director or authorised person (T3.3) · financial statements and auditor's report enclosed
(T3.4) · AGM held within the deadline (T3.7) · auditor attendance recorded (T3.8).

**How it can be wrong.**
- The previous AGM date is a user-supplied fact we do not verify — and it is the input the
  fifteen-month limb depends on entirely.
- A company that took an extension in year N usually finds the fifteen-month limb binds in year N+1;
  if we take the extension as displacing both limbs we produce a deadline that is too late, which is
  the dangerous direction.
- OPC has no s.96 deadline at all. Emitting one would be a fabricated obligation.
- `_TIME`- and `commenc\w+`-style matching produced a **false PASS on six real AGM notices** by
  matching the *remote e-voting* window ("commences on Saturday, June 14, 2025, at 9:00 a.m.") — see
  the calibration run in `corpus/testdocs/MANIFEST.md`. Any notice check reusing that pattern
  inherits the bug.

**Must refuse.** To emit a deadline for an OPC · to decide whether an extension displaces the
fifteen-month limb (carry it, extend only on an order supplied as input) · to compute from `PARTIAL`
text · to state a deadline while `missing_facts` is non-empty (`checker/matter.missing_for_agm()`
names them *before* the computation, not after) · to fire a day-count shortfall as a penalty-backed
finding — `RULES.md` records **essentially zero** orders for numeric shortfall; the two s.101 orders
are "no notice at all" and "oral notice" · to say the company is compliant. `VERIFIED` means the
evidence chain is complete, not that the law was obeyed.

**Cost: MEDIUM.** The deadline half is done. The build is (a) a notice-audit pass over the nine real
notices, (b) the VC/OAVM conditionality for T3.2, (c) one screen that takes a file and a date and
prints the card. `checker/documents.py` already emits print-ready HTML with correct `@page` rules
and no system dependencies, so the output path exists.

---

### W2 — "Is the template I've been using since 2019 still right?"

**In their words.** *"I've got a folder of Word precedents. I don't know when I last checked them
against the Act."*

**Trigger.** Reusing last year's document for this year's meeting; inheriting a predecessor's
precedent folder; a new matter of a type the practitioner has done before; a junior returning a
draft built from a template.

**Frequency.** Every time a document is drafted from a precedent — plausibly the **most frequent
document event in a small practice**, because a small practice drafts from precedent almost
exclusively. **ASSUMED, and this is the load-bearing assumption of the whole workflow.** Persona
claim B3 ("won't delegate drafting because juniors miss amendments") is from a **simulated** persona
and is explicitly labelled a hypothesis in `research/CLAIMS_TO_TEST.md`. No practitioner has said
this to us.

**Sections and rules.** Whatever the template cites. The canonical demonstrable case is
**s.139(1) first proviso — auditor ratification — omitted by Act 1 of 2018 s.40 w.e.f. 7 May 2018**.
Also SS-1 as amended in 2017 (director's-report attendance disclosure deleted).

**Verifiable today — and this is the unusual part.** We do not need a user's template to demonstrate
the workflow, because **the standard-setter's own specimen is stale and we have already proved it.**
`corpus/testdocs/MANIFEST.md` records, verbatim and with page references, that ICSI's published
specimen AGM notice (GN General Annexure II, p.131) and specimen AGM minutes (Annexure XVI, p.163)
both still carry:

> "...*(subject to ratification of their appointment at every AGM)*, at a remuneration of
> Rs. _______/- ... plus reimbursement of out of pocket expenses and **service tax**, as applicable."

Two independent staleness markers in one sentence: an obligation omitted 7 May 2018, and a tax
subsumed into GST on 1 July 2017. `checker/commencement.py` holds the commencement instrument;
`corpus/sources/commencement/2018-05-07.json` is in the repo.

**That is a demo that requires no user document, no interview and no new acquisition** — a
practitioner watching it sees their own institute's template fail. It is, in my reading, the single
most persuasive artefact this repository contains, and it is currently sitting inside a manifest
nobody outside the repo will read.

**Blocked.**
- **We hold zero user templates.** The mapping step — "which statutory hooks does this Word file
  rely on" — is unmeasured and unbuilt. `docs/FEATURE_PLAN_INDIA.md` F7 rates it LOW-MEDIUM for
  exactly this reason.
- **Detection is unmeasured in both directions.** We can show one true positive. We cannot state a
  false-positive rate, and `R-008` records that false negatives have **never been measured** because
  every document in the corpus is compliant.
- Templates arrive as `.docx` and, per every interview, often as paper. `.docx` intake is unbuilt;
  OCR is untested (`FEATURE_PLAN_INDIA.md` §4 marks it "not yet", not "never").

**Deterministic checks available.** Abolished-obligation detection against a register of provisions
omitted with instrument + clause + commencement (F5) · `STALE_TEXT` — holding live text for a
provision the source marks omitted, already implemented in the checker · version-dating every SS
check to the SS edition and date range it is valid for (mandatory per the Stanley Lifestyles Regional
Director decision, `RULES.md`) · qualifier preservation against the user's own sentence
(`checker/entail_qualifier.py`, `checker/review_table.py`).

**How it can be wrong.**
- An obligation omitted from the Act may be **re-imposed by a Rule, a notification or a listing
  regulation we do not hold**. We hold the Act, two Rules sets and SS-1/SS-2 — nothing else. A
  suppression phrased as "you do not need to do this" would be a legal conclusion drawn from an
  incomplete corpus.
- A template may deliberately over-provide. Recording auditor ratification in 2026 is stale; a
  belt-and-braces clause the client asked for is not a defect.
- Extraction fragility is proven, not hypothetical: `routemobile_22nd_agm_notice_2026.txt` extracts
  letter-spaced (`T w e n ty  S e c o n d`) and defeats every `\b`-anchored regex we have;
  `tataelxsi_37th_agm_notice_2026.txt` carries ligatures (`beneﬁt`, U+FB01).

**Must refuse.** To suppress an obligation on a footnote alone with no commencement instrument · to
suppress anything outside the Companies Act 2013 and the Rules we hold · to say "this clause is
wrong" — only "this Act provision imposed no such duty on that date, and we hold only the Act" · to
rewrite the template. Generation is commoditised and explicitly not our business (`CLAUDE.md`).

**Cost: MEDIUM.** The staleness demo is **small** — days, because the finding already exists and
needs only a card around it. The general "upload your own template" version is medium-to-large and
should not be attempted until the demo has been shown to a practitioner.

---

### W3 — "Have we got the board meetings right for the year?"

**In their words.** *"Four meetings, and the gap. Are we clean for FY 2025-26?"*

**Trigger.** Year-end compliance review; preparing the board's report; a secretarial auditor's
question; onboarding a client whose prior-year records are unknown; scheduling next quarter's meeting.

**Frequency.** At minimum four board meetings per company per year (s.173(1)) and the review at
least annually. Persona claim T6 asserts *96 sets of minutes a year across 8 SPVs* — **SIMULATED,
listed as a claim to refute in `research/CLAIMS_TO_TEST.md`, and it is exactly the kind of specific,
convenient number that document warns against.** **ASSUMED.**

**Sections and rules.** s.173(1) — four meetings, first within 30 days of incorporation, **not more
than 120 days** between consecutive meetings (a **ceiling**) · s.173(5) — one meeting per half
calendar year, gap **not less than 90 days** (a **floor**), for OPC/small/dormant · s.173(5) proviso
disapplying s.173 and s.174 for a single-director OPC · s.174 quorum · s.173(3) seven days' notice
(penalty is **s.173(4): ₹25,000 per officer, no company penalty** — a different shape) · s.118 and
SS-1 for the minutes.

**Verifiable today.** `checker/s173_slice.py` is **built**, with the floor/ceiling distinction held
explicitly in the type system (`CEILING`/`FLOOR` on every finding) and a module docstring explaining
why. It was authorised only after the entailment work learned floor-from-ceiling and within-clause
role binding. Regime selection by company class, per-finding direction, limit, observed value and
citation all render. Quorum is **surfaced as an open dependency, never assumed**.

**Blocked.**
- **No demo script.** `scripts/` has `slice_s96.py` and no `slice_s173.py`. The second working slice
  cannot currently be shown to anyone.
- **`company_class` is an input we take on trust.** It should come from W7, which is blocked on an
  unacquired rule. Today the caller asserts "small company" and we believe them.
- **"Every year" in s.173(1) is undefined.** s.173(5) says *calendar* year; SS-1 treats s.173(1) as
  calendar; **the Act does not say so** (`COMPLIANCE_MECHANICS` §4 item 3). This must be a visible
  policy switch and must never be silently picked.
- **Zero real minutes.** `corpus/testdocs/minutes_extracts/` is **empty**. Minutes books are not
  public and none was sought. Our only minutes are ICSI's five blank specimens. The four Route Mobile
  Reg 30 "outcome of board meeting" filings are the only real filed text stating both commencement
  and conclusion times — a fortunate substitute, not the real document.
- Notice periods, VC eligibility and the s.8 relaxation are **deliberately not built**.

**Deterministic checks available.** Count of meetings in the year · gap between consecutive meetings
against the **correct direction** for the regime · one-per-half-calendar-year for the relaxed regime ·
first meeting within 30 days of incorporation · s.174 quorum recorded as an open question rather
than certified (`C.quorum` in `checker/ss/defects.py` correctly PASSes on minutes specimens and
DEFECTs on Reg 30 outcome letters, which genuinely do not recite quorum).

**How it can be wrong.** The catastrophic mode is documented and defended against: a verifier blind
to direction reads the **relaxed** regime as satisfied by meetings held thirty days apart — turning a
defect into a clean bill of health. Beyond that: wrong company class propagates to every finding;
single-director OPC status is taken as given; a meeting held but not minuted is invisible to us; a
meeting adjourned and reconvened may be one meeting or two and we do not decide it.

**Must refuse.** To certify a meeting as **validly held** — that is s.174 quorum and this module does
not compute it · to assess notice periods, VC eligibility or the s.8 relaxation · to pick a
calendar-vs-financial-year reading silently · to report `COMPLIANT` on count and gap alone.

**Cost: SMALL.** The engine exists and passes. What is missing is a demo script and an input path —
days, not weeks. It is the cheapest genuine capability we own and the second-cheapest thing to put
in front of a tester.

---

### W4 — "The secretarial auditor / the ROC is going to look at the minutes book"

**In their words.** *"They want the minutes book. Is there anything in it that's going to cost us?"*

**Trigger.** A secretarial audit (MR-3); an ROC inspection or a s.206 notice; a
s.454 adjudication show-cause; buy-side due diligence asking for minutes; the annual
"has the company complied with applicable Secretarial Standards" statement in the board's report.

**Frequency.** **The only workflow in this backlog with real frequency evidence — and it is
enforcement frequency, not workflow frequency.** `checker/ss/RULES.md`, from 68 distinct s.454
adjudication orders 2021–2026: ~20–25 s.118 / Secretarial Standards orders reach publication per
year, roughly **4%** of all published adjudication orders. Filing defaults (s.92/s.137) dominate at
**16.2%**. 2026 is on pace to match or exceed 2025 at eight months in. **How often a practitioner
reviews a minutes book is ASSUMED and unmeasured.**

**Sections and rules.** s.118(10) makes SS-1 and SS-2 mandatory · s.118(11): **₹25,000 on the company
and ₹5,000 on every officer in default**, with **no per-day continuing element** (the e-adjudication
"Additional Penalty per day" column reads 0 in every s.118 order in the corpus) · s.446B halves it
for small companies, start-ups, OPCs and producer companies · SS-1 clauses 4.1, 7.1.4, 7.4, 7.5.2,
7.6 · SS-2 clauses 17.1.4, 17.2.2.1(o), 17.4.2 · Rule 25(1)(b) Companies (Management and
Administration) Rules 2014 · s.134(5)(f) for the board-report statement · s.102(5) and s.450 for the
notice-side checks.

**Verifiable today — the rules.** This is our strongest legal research. Every rule in `RULES.md` is
backed by at least one real penalty order; rules with zero precedent are quarantined as advisory.
The three multiplication axes are evidenced by name: **per meeting** (Trouw Nutrition, ₹25,000 × 54
board meetings + ₹25,000 × 7 general meetings ≈ **₹21.35 lakh**), **per financial year** (Anheuser
Busch InBev ₹1,50,000 over three FYs), **per book on the same day** (Om Shyamji Foods, three separate
orders on 18.12.2025 — Board, AGM and EGM books; Rosmerta Autotech, five orders on 09.10.2025). And
**every defence in the corpus has failed** — voluntary disclosure, rectification before the order,
"procedural lapse, no mala fide intent", records lost to a flood — with one exception (Tamilnad
Mercantile Bank, saved by SS-1 7.4(v) deemed approval). The value proposition is therefore
*pre-emptive only*, and that is a finding, not a slogan.

**Blocked — and this is where the workflow currently fails.**
- **The highest-frequency check class is permanently unreachable by any document scanner.**
  T1.1 (pagination consecutive across the *whole book*), T1.2 (Chairman's initials on every page) and
  T1.3 (blank pages scored out) are properties of a **bound physical book**, together **~24 of the 68
  orders** — the single largest defect class. `corpus/testdocs/MANIFEST.md` is explicit: this cannot
  be fixed by adding PDFs. The Rosmerta Technologies defect was numbering that *restarted each
  financial year* across a multi-year book, which no single extracted document can exhibit.
  `defects.py` correctly returns `NEEDS_BOOK`. **This boundary must be stated to a professional up
  front, not discovered by them.**
- **The scanner over-fires badly on real documents.** Calibration over 18 documents:
  **T1.6a fires DEFECT on 18 of 18, including all five of ICSI's own specimen minutes — a 100%
  false-positive rate**, because `_SERIAL` requires `Meeting No: 14`, the phrasing in the author's own
  fixture, while real Indian practice writes an ordinal in the title. T1.7 produces a **false PASS on
  a penalty-backed check** by matching the bare word "place" anywhere in prose. T1.8 matches the
  roman-numeral list marker `i`. `R-003` records T1.4a/T1.6a/b/c/T1.7 as still over-firing.
- **False negatives have never been measured** (`R-008`) because every corpus document is compliant.
- **We hold zero real minutes and zero deliberately-defective documents.** MCA blocks automated
  fetches (HTTP 403) so no ROC order text — the only realistic source of *defective* real minutes —
  is in this repo. `B-001` is marked **CRITICAL PATH** and is open.

**Deterministic checks available.** T1.4 (entry within 30 days, date of entry recorded — highest
financial exposure) · T1.5 (correct signatory: chairman of the meeting *or* of the next; never a
third director "on behalf of", per Landomus; never the earlier chairman where the standard requires
the subsequent, per Dystar) · T1.6 (serial number, day, **time of commencement and conclusion** —
conclusion is the commonly missed half) · T2.1 board-report SS statement · T2.2 attendance register ·
T2.3 draft minutes within 15 days with the 7.4(v) deemed-approval carve-out as a mitigating flag ·
T2.4 proof of dispatch (Anheuser Busch and AVK Valves were penalised purely for inability to
**produce** proof) · exposure arithmetic per meeting / per book / per FY with the s.446B halving.

**How it can be wrong.**
- Over-firing by document type is not hypothetical: **80–93% false positives** were observed when
  minutes checks ran against notices. Gating exists and is incomplete.
- Version drift: a check firing against a repealed SS requirement is the Stanley Lifestyles error,
  where the Regional Director held a penalty unwarranted because SS-1 had been amended in 2017.
- A false PASS on a penalty-backed check (T1.7 today) is worse than a false DEFECT, because the
  practitioner stops looking.
- `tcpl` vs `tataelxsi` shows a real trap for T2.1: Tata Elxsi says it has *"devised proper systems
  to ensure compliance"*, not *"has complied"*. A check keyed to "has complied" passes two and
  misses the third — and all three are the standard s.134 statement.

**Must refuse.** To fire as penalty-backed any rule with zero precedent — route map / venue
particulars in an AGM notice, failure to record leave of absence, failure to record dissent, numeric
day-count shortfall: **zero orders across 1,609 tagged**, advisory only and labelled · to return PASS
on a physical-book property (`NEEDS_BOOK`, always) · to claim "high enforcement risk" — claim what the
corpus supports: the defence has never worked, the penalty multiplies, it is entirely preventable ·
to present a s.454 *penalty* and a criminal *fine* (s.99, s.129(7), s.147) identically.

**Cost: LARGE, and it is rework, not extension.** Adding checks to a scanner with a 100% FP Tier-1
rule increases the noise. The order is: fix `R-003`, acquire defective documents (`B-001`), then
measure. Do not ship this workflow to a practitioner before that; a false PASS on a ₹21-lakh exposure
class is the worst single outcome available to this product.

---

### W5 — "What did the section actually say in March 2019?"

**In their words.** *"This resolution is dated 2019. I need the section as it stood then, not now."*

**Trigger.** Due diligence on a past transaction; an ROC notice about an old default; a dispute over
a historical filing; regularising a client's prior years; a secretarial audit covering an earlier FY.

**Frequency.** **Genuinely unknown, and this is the highest-stakes unknown in the backlog.**
`research/CLAIMS_TO_TEST.md` names B2 as *"the claim that would most change the plan"*: if
experienced practitioners answer a past-date question in under two minutes from memory or one source,
amendment reconstruction is not a product; if they cannot answer it at all, it is the whole product.
Persona claim T3 (a ₹5,000/day research assistant for historical work) is flagged as **the claim most
expected to be wrong**. **ASSUMED, and knowingly untested.**

**Sections and rules.** Any. The proved boundaries are s.177, s.447, s.35, s.96.

**Verifiable today.** Boundary behaviour is **proved** — 6/6 boundaries on s.177, s.447 and s.35, text
changing across each, effective dates inclusive (`scripts/prove_temporal.py`, `docs/TEMPORAL_PROOF.md`).
`checker/commencement.py` distinguishes a footnote w.e.f. date from the notification that appointed
it, and shows both where they diverge. `checker/timeline.py` holds 434 amendment records from India
Code's own footnotes, 431 with a w.e.f. date. **Prior wording is independently corroborated for the
first time**: 24 amended spans matched against the amending Acts themselves on Indian Kanoon,
**0 conflicts**, 21/24 where the instrument is held (`docs/CORROBORATION.md`).

**Blocked.**
- **Section-level reconstruction of substituted spans is UNVERIFIED.** Corroboration covers
  individual *spans*, not whole sections — the exact distinction the retracted claims missed
  (`docs/RETRACTIONS.md`). Two known-invalid results must never be cited: "119/119 EXACT vs
  as-enacted print" (the reference was the current consolidation) and "43/43 prior wordings found in
  the PDF" (circular).
- **Indian Kanoon does not host The Companies (Amendment) Act, 2019**, so claims resting on Act 22 of
  2019 have no witness there — 9 of 16 unresolved cases.
- Ten genuine unclosed India Code spans remain (SD-003), **at least eleven** counting the s.92 defect
  found independently in the `COMPLIANCE_MECHANICS` harvest. SD-004 (s.174(1) "hall be one-third")
  has no independent witness and blocks a rule promotion (`S-001`).
- Corpus status is **NOT_FULLY_VERIFIED**; independent-publisher verification is **PENDING**. Both our
  renderings are India Code, so a defect in their own source is invisible to our cross-render check.

**Deterministic checks available.** `text_fidelity` EXACT / PARTIAL / ABSTAIN · commencement
instrument + list item + sha256 · amendment count in force at the as-of date · `STALE_TEXT` detection ·
source-defect disclosure preserved verbatim, never repaired.

**How it can be wrong.** Serving a reconstruction as verified when only a span is corroborated is the
mistake already made once and retracted. A footnote w.e.f. date that the notification does not support
is a real divergence class we have seen (S.O. 1833(E)). An amendment omitted from India Code's
footnotes is invisible to us entirely.

**Must refuse.** To present a reconstruction as verified against any external source · to compute from
`PARTIAL` text · to repair a defective government source · to answer for any statute other than the
Companies Act 2013.

**Cost: MEDIUM as a row expansion (F8/F9/F11), LARGE as a standalone product.** Build it as the
expansion behind a W1/W3 row, not as a "historical law browser" — s.52(1)(q)(ii) forbids serving Act
text without original matter, and a browser is the fastest route to breaching it.

---

### W6 — "Client's AGM was held on the 12th. What's due now, and by when?"

**In their words.** *"AGM was 12 September. AOC-4, MGT-7, ADT-1 — dates please."*

**Trigger.** The AGM concluding; a client asking for the year's filing calendar; taking on a company
with unknown filing history; an additional-fee notice arriving.

**Frequency.** Once per company per year, in a September–November cluster. Persona claim T5 (40 forms
per quarter) is **simulated**. **ASSUMED.** However: **filing defaults are the largest published
enforcement class at 16.2% of orders**, four times the SS class — so if enforcement volume is a proxy
for how often this goes wrong, this is the most-wrong workflow in Indian corporate compliance.

**Sections and rules.** s.137(1) AOC-4 within 30 days of the **actual** AGM; second proviso for
adjourned adoption; **third proviso, OPC 180 days from FY close** · s.137(2) AOC-4 where no AGM was
held: AGM-due + 30 days · s.92(4) MGT-7 within 60 days of the actual AGM; MGT-7A for OPC and small
companies; where no AGM was held, AGM-due + 60 days · s.139(1) and r.4(2) ADT-1 within 15 days ·
s.92(5), s.134(8), s.137(3) — s.454 penalties · r.7 Companies (Miscellaneous) Rules 2014, MSC-3 for
dormant companies.

**Verifiable today.** `docs/COMPLIANCE_MECHANICS.md` §1 holds the full statute-fixed vs
company-chosen split with each formula and its provision, derived from a harvest of India Code's
1,183 holdings for the Act. `checker/derived_date.py` verifies the interval phrase verbatim against
the cited provision before deriving. The **OPC 180-days-is-not-six-months** trap is documented
(31 March + 180 days = 27 September, not 30 September — compute in days).

**Blocked.**
- **The forms are governed by rules we do not hold.** `corpus/rules/` contains exactly one instrument
  (`board_powers_2014.json`) and `corpus/provisions/` holds the Accounts Rules 2014 plus PoSH-era
  material. The **Companies (Management and Administration) Rules 2014** (MGT-7/7A), the
  **Audit and Auditors Rules 2014** (ADT-1), and the **Registration Offices and Fees Rules** (the
  additional-fee ladder that makes a missed date cost money) are **all unacquired**.
- Whether MGT-7 or MGT-7A applies depends on small-company status, which is **W7, which is blocked**.
- `COMPLIANCE_MECHANICS` §4 item 2: the OPC annual-return deadline has no anchor — s.92(4) has no OPC
  limb and s.96 does not apply, so no "should have been held" date exists.
- §4 item 8: first-auditor ADT-1 — s.139(6) contains no notice obligation and r.4(2) is tied to
  s.139(1). Advisory only.
- `docs/FEATURE_PLAN_INDIA.md` §4 declines a **generic deadline calendar with push alerts**, and the
  reasoning holds: a confidently wrong reminder is worse than none, and this is exactly where
  auditor-ratification-style false positives are manufactured. This workflow must be built as
  *dated obligations with evidence*, never as notifications.

**Deterministic checks available.** All eight statute-fixed formulas in `COMPLIANCE_MECHANICS` §1 ·
the actual-AGM-date-dependent formulas once the date is supplied · penalty-vs-fine classification ·
`NO_EVIDENCE_HELD` rows for filings with no document behind them, which is the most valuable value in
the matrix.

**How it can be wrong.** Computing months where the statute says days (OPC). Using the AGM *due* date
where the statute says the *actual* date, or the reverse. Assuming MGT-7A on an unverified
small-company status. Treating an adjourned AGM's original date as the trigger.

**Must refuse.** To compute an additional fee — the fee rules are unacquired and a wrong rupee figure
is a specific, checkable lie · to emit a deadline for a form whose governing rule we do not hold · to
push a reminder · to state a filing was *made* — we hold no MCA filing data.

**Cost: MEDIUM**, plus acquisition. The date arithmetic is small. Acquiring three rule sets under
`docs/ACQUISITION_POLICY.md`, with MCA blocking automated fetches, is the real cost and is partly
human-gated.

---

### W7 — "Is this company small?"

**In their words.** *"Private company, ₹35 lakh capital, ₹3.5 crore turnover — small or not?"*

**Trigger.** Onboarding a client; deciding MGT-7 vs MGT-7A; deciding the s.173(5) relaxed regime;
deciding whether the abridged board report applies; deciding whether s.446B halves an exposure.

**Frequency.** Once per company per financial year at minimum — status is **re-tested annually and is
not sticky**. It gates W3, W4 and W6, so its effective frequency is the sum of theirs. **ASSUMED.**

**Sections and rules.** s.2(85) with both provisos · **G.S.R. 700(E), Companies (Specification of
Definition Details) Amendment Rules 2022, 15-09-2022** — which sets the operative amounts ·
**S.O. 504(E), 13 Feb 2015**, which substituted "and" for "or" between the two limbs · the s.2(71)
proviso (a private subsidiary of a public company is a public company for the whole Act) · s.2(41)
financial year · **para 2A of G.S.R. 464(E) as inserted by G.S.R. 583(E)** · MSC-2 for dormant status.

**Verifiable today.** `checker/company_profile.py` and `checker/classify.py` are **built**, with the
correct asymmetry encoded: NOT SMALL needs one definitive failing condition; SMALL needs every
condition KNOWN and satisfied, because being small is a **relief** and a wrong "small" is the
dangerous direction. Money is whole rupees with `lakh()` and `crore()` constructors, because ₹4 crore
entered as "4" passes every "does not exceed" test ever written. A figure is bound to its financial
year, so a comparison against the wrong year is refused rather than computed. There is deliberately
**no `is_small_company` field** — a stored flag drifts from its inputs.

**Blocked — hard, and with a named human fix.** The operative thresholds are not in the Act; s.2(85)
states a floor and a ceiling and delegates. **The widely-cited ₹4 crore / ₹40 crore appear nowhere in
the Act.** `checker/prescribed_thresholds.py` therefore returns `INSUFFICIENT_DATA` on the arithmetic
today, and that refusal is correct. Both official acquisition routes are blocked:
`indiacode.gov.in/robots.txt` returns **HTTP 502** and `checker/robots.py` fails closed (a 4xx means
no rules exist; a 5xx means we cannot know what they are), and egazette sends no intermediate
certificate and chains to a root absent from this machine's trust store. The instrument is located —
India Code handle `123456789/508916`, text bitstream uuid `6d5e9902-…`, 5153 bytes. **Task `S-002`,
terminal state `HUMAN_RETRIEVAL_REQUIRED`: a person downloads it in a browser and runs
`python3 scripts/register_gsr700e.py <file>`.**

> This is the highest-leverage single human action available. It is one download, and it unblocks the
> arithmetic that gates W3's regime, W4's s.446B halving and W6's MGT-7A choice.

**Deterministic checks available.** Public-company exclusion (no threshold needed) · holding /
subsidiary / s.8 / special-Act exclusions · the s.2(71) proviso · the conjunctive two-limb test with
the two limbs drawn from **different periods** (capital as at, turnover from the *immediately
preceding* FY) · the para 2A exemption gate (`OPEN` / `COLLAPSED` / `UNKNOWN`, defaulting to
`UNKNOWN`).

**How it can be wrong.** Unaudited denominators — the rule supplies none, so return "cannot
determine" and **never substitute**. A default flag the user reports rather than one we verify (we
hold no MCA filing data, so `exemption_gate` is honestly `UNKNOWN` for every real company). Group
structure the user describes incompletely. Treating status as sticky.

**Must refuse.** To use the ₹4 crore / ₹40 crore figures until G.S.R. 700(E) is registered and hashed
· to guess a default flag · to use unaudited figures as a denominator · to default an unknown figure
to zero, because for a "does not exceed" test zero is the strongest possible pass and defaulting
converts ignorance into a favourable answer.

**Cost: SMALL once unblocked** — the classifier is written and the threshold table has a slot waiting.
**Infinite until then**, by design.

---

### W8 — "Does this related-party transaction need board approval or members' approval?"

**In their words.** *"Director's brother's firm, ₹80 lakh contract. Board resolution enough, or do we
need an ordinary resolution?"*

**Trigger.** A proposed contract with a related party; an auditor flagging an unapproved RPT; a board
agenda item; the AOC-2 annexure to the board's report.

**Frequency.** Event-driven, unpredictable, and **ASSUMED**. Higher in group and family-owned
structures, which is most of the private-company population — **UNVERIFIED**.

**Sections and rules.** s.188(1) and its provisos · s.188(3) ratification within 3 months of the
contract date · s.188(5) penalty · **Rule 15 Companies (Meetings of Board and its Powers) Rules 2014**
· s.184(1) and r.9 MBP-1 · s.2(76) related party, s.2(77) relative.

**Verifiable today.** This is the **one subordinate instrument we actually hold in full**:
`corpus/rules/board_powers_2014.json`, gazette-provenanced and hashed. `COMPLIANCE_MECHANICS` §2
documents three traps that a generic tool gets confidently wrong:
- **Rule 15(3) operators differ by clause.** Clause (a) items (i)–(iv) are `>=` ("ten per cent or
  more") **since G.S.R. 309(E), 30 Mar 2017**; before that, `>`. Clauses (b) and (c) remain strictly
  `>`. One operator applied uniformly gives a wrong answer at exactly the boundary.
- **The rupee caps were removed mid-year** by G.S.R. 857(E), 18 Nov 2019. **FY 2019-20 is split** —
  transactions before that date use the capped test, from that date the uncapped. Date-stamp each
  transaction; do not batch by year.
- **Denominators are historical and audited** — turnover and net worth from the *audited* statement of
  the *preceding* year.

**Blocked.** §4 item 5: Rule 15(2) bars an interested director's *presence* for RPT discussions while
G.S.R. 464(E) Sl.13 lets a private company's interested director *participate* — **no resolving
instrument located; surface both**. §4 item 6: whether Rule 15(3) aggregation is per related party or
across all is **not stated in the rule** — default to the stricter reading. And the para 2A gate
(W7) decides whether the G.S.R. 464(E) relief is even available.

**Deterministic checks available.** Clause-specific operators with the correct instrument date ·
mid-year cap split · audited-denominator precondition · the 3-month s.188(3) ratification window ·
MBP-1 as event-triggered on a board meeting with no fixed date.

**How it can be wrong.** Applying today's operator to a 2016 transaction. Batching FY 2019-20.
Substituting an unaudited denominator. Deciding the presence-vs-participation conflict.

**Must refuse.** To resolve §4 items 5 and 6 · to compute a percentage from unaudited figures · to
state whether a person *is* a related party where the family relationship is asserted and not
evidenced.

**Cost: MEDIUM.** The rule is held and the traps are documented; the work is the operator/date matrix
and the transaction-level date stamping. Do it after W7, because the denominators and the exemption
gate both come from there.

---

### W9 — "Company was incorporated last month. What's due in the first 90 days?"

**Trigger.** Incorporation certificate issued.
**Frequency.** Once per new company. **ASSUMED**; volume depends entirely on whether the practice does
incorporation work, which no interview tells us.
**Sections.** s.173(1) first board meeting within **30 days of incorporation** · s.139(6) first auditor
within **30 days of registration** · s.96(1) first proviso, **first AGM within 9 months of the first
FY close** · s.2(41) (a company incorporated on or after 1 January gets a longer first financial year,
so the FY is **not derivable from a date alone**).
**Verifiable today.** All three formulas are statute-fixed and in `COMPLIANCE_MECHANICS` §1 — no
carried state, no user-chosen dates, so it is the **cleanest arithmetic in the whole Act**.
`checker/s96_slice.py` already carries `is_first_agm`.
**Blocked.** ADT-1 for the first auditor is advisory only (§4 item 8: s.139(6) has no notice
obligation and r.4(2) is tied to s.139(1)). SPICe+/INC-20A are governed by rules we do not hold.
**Checks.** Three date derivations, each with its interval verified verbatim against the provision.
**Wrong / refuse.** The s.2(41) first-FY rule is the trap — never derive the financial year from the
incorporation date alone. Refuse to state anything about SPICe+ or INC-20A.
**Cost: SMALL.** Genuinely a few days. But it is a **once-per-company** workflow with no recurrence,
so it earns loyalty poorly. Cheap filler, not a wedge.

---

### W10 — "The bank sanctioned the loan. Charge has to be filed in 30 days."

**Trigger.** Creation or modification of a charge.
**Frequency.** Event-driven; high for lenders' counsel, low elsewhere. **ASSUMED.**
**Sections.** s.77 (30 days, extendable on payment of additional fees within statutory outer limits) ·
s.78, s.79, s.82 satisfaction · CHG-1/CHG-4.
**Verifiable today.** Essentially nothing. The section is in the corpus; the deadline arithmetic is
trivial.
**Blocked.** The **Companies (Registration of Charges) Rules 2014 are not held**, and s.77's extension
ladder is precisely where the fee and outer-limit detail lives. Building the deadline without the rule
would produce a confident date that misses the extension mechanics.
**Why it is in the list at all.** It has the shortest hard deadline and one of the harshest
consequences in the Act — an unregistered charge is not taken into account by a liquidator — so per
*instance* it is high value. But we can evidence none of it today.
**Cost: MEDIUM**, mostly acquisition. Not now.

---

### W11 — "Adding a director. What do we need?"

**Trigger.** Board decides to appoint; a director resigns; annual DIR-3 KYC season.
**Frequency.** DIR-3 KYC is annual per director and is one of the very few items with a *confirmed*
staleness signal in our own research: `R-005` records **one confirmed SUPERSEDED claim — DIR-3 KYC**.
That is n=1 and is the only such confirmation we hold.
**Sections.** s.152, s.161, s.164 disqualification, s.167 vacation of office, s.168 resignation ·
Companies (Appointment and Qualification of Directors) Rules 2014 — **not held**.
**Blocked.** The governing rules are unacquired; DIN and KYC procedure is almost entirely subordinate
legislation and MCA process, and MCA blocks automated fetches.
**Refuse.** To state a DIR-3 KYC due date or procedure from a corpus that does not contain the rule.
**Cost: MEDIUM**, mostly acquisition. Not now.

---

### W12 — "Secretarial audit for the year"

**Trigger.** Applicability under s.204 read with the Managerial Personnel Rules.
**Why it is not near the top despite obvious fit.** s.204 secretarial audit applies to **listed
companies and prescribed classes** — i.e. companies large enough to have exactly the infrastructure
our target user does not have. Our brief is practitioners **without** big-firm infrastructure; the
clients driving MR-3 are not their clients. It is also a **CS-only** function, which collides with the
`PRODUCT_SCOPE` lawyer decision (§0.2).
**Cost: LARGE.** It is a superset of W1, W3, W4 and W6. Build the parts; do not target the whole.

---

### W13 — "Due diligence on the target's corporate records"

**Trigger.** Term sheet; investment; acquisition.
**Value: very high** — it is where corporate lawyers concentrate and where a missed defect is priced.
**Why it is not buildable now.** It is a **document-mass** workflow, and `docs/FEATURE_PLAN_INDIA.md`
§0 is explicit that our user has no document mass; building for an asset the customer does not own is
the mistake that plan exists to avoid. It also needs the target's minutes, registers and filings — none
of which we can obtain, and `CLAUDE.md` forbids seeking private minutes.
**Cost: LARGE.** Revisit only if the customer turns out to be a firm doing deals, which contradicts
"without big-firm infrastructure".

---

### W14 — "Is this counterparty who they say they are?"

**In their words**, verbatim from the only company-side interview we have:
*"GST number डालने का — सामने वाली पार्टी को authenticate करके दे सकें"* · *"account number दे दिया और नाम अलग
दे दिया… इसमें बहुत बड़ा fraud हो जाता है"* · and what he wants at the end: **"एक verified का sign लग जाए"**.

**This is the only workflow in this entire backlog that a real user asked for, unprompted, and
returned to three times.** Everything else here is our inference from statute and enforcement data.
That asymmetry deserves to be stated rather than buried.

**Why it is nonetheless not in the top three.** It is not Companies Act work and not legal AI — it is
vendor onboarding and fraud prevention, with funded incumbents (Signzy, IDfy, Karza/Perfios, Surepass
— **UNVERIFIED**, from the interview note, not from vendor sources) and restrictive PAN-verification
eligibility rules. `CLAUDE.md` scopes this product to the Companies Act 2013. The feasibility check
described in the interview note has **not returned** in anything recorded in either repo.

**What is adjacent and already ours:** OGD company master data, CIN → name, capital, status, 3.67M
records, ₹0, described as **verified live** in the interview note. A CIN lookup with an as-at date and
a provenance stamp is the same architecture pointed at a counterparty, and it is **small**.

**Cost: MEDIUM** for the full ask; **SMALL** for the CIN-lookup sliver. Recorded, not scheduled.

---

## 3. Build these first

### 1. W1 — the AGM cycle

Build this first because it is the only workflow where the deadline engine, the real documents and a
runnable demo already exist in the same place. `checker/s96_slice.py` passes, `scripts/slice_s96.py`
runs it, `checker/agm.py` verifies the interval phrase against the provision before deriving, and
`corpus/testdocs/agm_notices/` holds nine real notices from five listed issuers against which
T3.1, T3.3, T3.5 and T3.7 can be exercised today. It also contains the highest-value single check we
own: T3.1, special business genuinely classified as special with an explanatory statement, carrying
the largest per-officer figure in the 68-order corpus at ₹50,000 per director. The workflow has a
natural annual trigger, a natural output (a printable card a partner reads and a file note quotes),
and a hybrid deadline rule — `MIN(FY_close + 6 months, previous_AGM + 15 months)` — that generic
calendars get wrong because the fifteen-month limb needs state carried from last year. The honest
caveats travel with it: our notices are all listed large- and mid-cap issuers rather than the small
private companies we are aiming at, the Registrar-extension question is unresolved, and no
practitioner has told us this is their pain — we chose it and then wrote our own interview baseline
around it.

### 2. W2 — the precedent staleness audit

Build this second because we already hold the demonstration and have not yet used it. ICSI's own
published specimen AGM notice and specimen AGM minutes still carry *"(subject to ratification of their
appointment at every AGM)"* and *"service tax"* — an obligation omitted by Act 1 of 2018 s.40 w.e.f.
7 May 2018, and a tax subsumed into GST on 1 July 2017 — recorded verbatim with page references in
`corpus/testdocs/MANIFEST.md`, with the commencement instrument sitting in
`corpus/sources/commencement/2018-05-07.json`. A practitioner watching their own institute's template
fail a dated check needs no explanation of what statutory currency means, and the demo requires no
user document, no interview and no new acquisition. It is also the exact thesis in `CLAUDE.md` —
customising a template stops legal updates, so every firm's precedents are a private fork drifting
from the law, detectable only at the output. The scope discipline matters: build the *staleness card
around the finding we already have* first, which is days of work, and treat "upload your own Word
template" as a separate, later, medium-to-large piece whose mapping step is unmeasured and whose
intake is untested against the paper documents all four interviews describe.

### 3. W3 — the board-meeting year in review

Build this third because it is the cheapest genuine capability we own — the engine is written and
passing, and what is missing is a demo script and an input path, which is days rather than weeks.
`checker/s173_slice.py` holds the floor/ceiling distinction structurally, with `CEILING` and `FLOOR`
on every finding, which defends against the single most dangerous error available in this section:
reading the relaxed s.173(5) regime as satisfied by meetings thirty days apart, turning a defect into
a clean bill of health. It surfaces s.174 quorum as an open dependency rather than certifying validity
on count and gap alone, which is exactly the abstention behaviour we want a sceptical practitioner to
see. Two constraints keep it at third rather than higher: `company_class` is an input we currently
take on trust and should come from W7, which is blocked on G.S.R. 700(E); and we hold **zero real
minutes**, so the year-review runs on dates the user supplies rather than on documents we can read.
Ship it as a dates-in, card-out review and be explicit that it does not read the minutes book.

**The one non-build action that outranks all three:** task `S-002` — a human downloads G.S.R. 700(E)
from India Code in a browser and runs `scripts/register_gsr700e.py`. It is one download, it takes
minutes, and it unblocks W7, which gates W3's regime selection, W4's s.446B halving and W6's
MGT-7/MGT-7A choice. Nothing else in this backlog has that ratio.

---

## 4. Workflows NOT to build first, and why

This list is about **sequencing**, not permanent refusal. `docs/FEATURE_PLAN_INDIA.md` §4 holds the
permanent refusals (clean-statute browser, document generator, compliance score, case-law citations,
automatic MCA filing, vault, vector search, chatbot, fine-tuning, scraping MCA) and is not restated
here.

| Not first | Why not, specifically |
|---|---|
| **W4 — the SS / minutes defect scan** | It looks like the obvious first build because it has the best legal research in the repo. It is not, for three reasons that are all in our own files. **T1.6a has a 100% false-positive rate on real documents** — it fires DEFECT on 18 of 18, including all five of ICSI's own specimen minutes. **T1.7 produces a false PASS on a penalty-backed check**, which is worse than a false DEFECT because the practitioner stops looking. And **~24 of the 68 orders — the largest defect class — are physical-book properties that no document scanner can ever reach**. Extending a scanner in this state adds noise to noise. Rework `R-003` and acquire `B-001` first. |
| **W6 — the annual filing chain** | Highest enforcement volume in the published-order data (16.2% vs SS at 4%), and still not first, because the three rule sets that govern the forms — Management and Administration, Audit and Auditors, Registration Offices and Fees — are **all unacquired**, MCA blocks automated fetching, and the MGT-7 vs MGT-7A choice depends on W7, which is itself blocked. Building it now means computing dates for forms whose governing rule we have not read. |
| **W7 — company classification** | Not a build decision at all. It is **one human download** (`S-002`). Scheduling engineering time against it before the instrument exists would produce a classifier that still answers `INSUFFICIENT_DATA`. |
| **W5 — point-in-time law as a standalone product** | It is the moat, and it has the **weakest demand evidence in the backlog**. `research/CLAIMS_TO_TEST.md` names B2 as "the claim that would most change the plan" and it is untested; T3 (the paid historical-research assistant) is flagged as "the claim I most expect to be wrong". Build it as the expansion behind a W1/W3 row, where it is already useful, and let the interviews decide whether it deserves its own surface. A standalone "historical law browser" is also the fastest available route to breaching s.52(1)(q)(ii). |
| **W10 charges · W11 directors** | Both are governed almost entirely by rules we do not hold. The deadline arithmetic is trivial and the arithmetic is not the product; the rule is. Acquisition first. |
| **W12 — secretarial audit** | Applies to listed and prescribed companies — clients who *have* the infrastructure our target user lacks. It is also a CS-only function, and `docs/PRODUCT_SCOPE.md` currently says the primary customer is a lawyer. Wrong customer size and an unresolved segment question at the same time. |
| **W13 — due diligence** | A document-mass workflow for a user with no document mass. It also requires the target's minutes and registers, which `CLAUDE.md` forbids seeking. |
| **W14 — counterparty verification** | The only user-originated ask we hold, and out of scope. It is fraud prevention, not Companies Act work; incumbents are funded; PAN-verification eligibility is restrictive; and the feasibility check described in the interview note has not returned anywhere in either repo. The **CIN-lookup sliver** is small, in-scope-adjacent and worth keeping visible. |
| **Any push-notification compliance calendar** | Named as a non-goal in the feature plan and the reasoning is sound: a confidently wrong reminder is worse than none, and a calendar is precisely the surface that manufactures auditor-ratification-class false positives. Dated obligations with evidence, yes. Alerts, no. |
| **OCR intake** | Not "never" — "not yet", and it is a live risk rather than a deferral. All four interviews say documents are physical (*"सब physical रहते हैं"*); every document in `corpus/testdocs/` is text-extractable. **Our corpus is the opposite of what our users describe.** Settled in one week by collecting 20 documents in the format they actually arrive in. |
| **Anything targeted at a Company Secretary before `R-011` closes** | Not because CS is the wrong segment — the one company-side interview named CS unprompted — but because `docs/PRODUCT_SCOPE.md` locked "lawyer, not CS" on 20 Aug and the market model is still CS-shaped and marked for rebuild. Building for a segment while the segment decision is contradicted in two files is how a product acquires two half-audiences. |

---

## 5. What would change this ranking

Nothing here is stable. In descending order of how much it would move the list:

1. **Five practitioner interviews using `research/INTERVIEW_KIT.md`.** Stage 2 alone — whether an
   experienced professional misses the fifteen-month limb, and what they do when asked the same
   question for FY 2018-19 — settles W1's value and W5's existence in a single afternoon. B2 is
   named in our own files as the claim that would most change the plan and it has never been asked.
   **Zero Company Secretaries have been interviewed**, and the buyer has now been named by two
   independent routes.
2. **`B-001` — 30–50 documents including deliberately defective ones.** Marked CRITICAL PATH in
   `research/TASKS.md`. It is the only thing that can measure false negatives (`R-008`) and it
   converts W4 from unshippable to shippable.
3. **`S-002` — one human download of G.S.R. 700(E).** Unblocks W7 and therefore parts of W3, W4 and W6.
4. **Twenty documents collected in the format they actually arrive in.** Settles OCR and file format
   in a week, and either confirms or destroys the intake assumption under W1, W2 and W4.
5. **`R-011` — rebuild the market model for the declared segment.** Until it closes, no workflow in
   this document can be sized, priced or pitched.
6. **`H-001` — review by one or two practising corporate lawyers.** Gates claims, not development.

**Frequency evidence status across this entire backlog: zero of fourteen workflows have an
evidenced frequency.** That sentence should be deleted only when an interview record exists that
contradicts it — not when it becomes inconvenient.
