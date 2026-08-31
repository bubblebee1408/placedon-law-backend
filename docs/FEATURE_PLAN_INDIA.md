# Feature plan — India-first, statute-first

Written 31 Aug 2026. Companion to `docs/PRODUCT_SCOPE.md` (what we are), `docs/NON_GOALS.md`
(what we refuse), `docs/COMPLIANCE_MECHANICS.md` (the engine rules) and `checker/ss/RULES.md`
(the enforcement evidence). This document decides **what to build and in what order**, and it
ranks by `(value to the user) / (evidence we can produce today)`.

No code here. Every guess is marked. No web search was available while writing this, so every
claim about the market, competitors, pricing or user behaviour is **UNVERIFIED** and labelled.

---

## 0. The inversion this plan is built on

Legora sells tabular review across many contracts. Harvey sells Vault across a large private
document store. Both monetise two assets:

1. **private document mass** — an iManage/NetDocuments/data-room corpus, and
2. **a firm playbook** — a house position to compare each document against.

*(Description of both products is from public material and prior notes in this repo. Neither
product has been used or tested by us. Treat every sentence about them as an architectural
inference, **UNVERIFIED**.)*

An Indian solo or small corporate practice has neither asset. It has a laptop, a folder of Word
precedents, a handful of client companies, and a statutory burden where the ground truth is
**public** — the Act, the Rules, the notifications, the Gazette. That public ground truth is:

- **dated** (footnote w.e.f. dates that do not always match the notification that supplied them —
  `checker/commencement.py`, S.O. 1833(E)),
- **unevenly commenced** (one amending Act commencing in stages across 2018-2021),
- **defective at source** (`docs/SOURCE_DEFECTS.md`: SD-001 editorial instruction inside s.1,
  SD-002 vintage divergence, SD-003 ten genuine unclosed spans, SD-004 `hall`/`maybe`
  transcription errors).

So the product is not "review your documents against your playbook". It is:

> **Given a company and a date, here is every obligation that bound it, what the law actually
> said on that date, which instrument made it say that, and what evidence you hold — or do not
> hold — for each one.**

The single design consequence, and the whole difference from tabular review:

> In tabular review, a row is **a document you have**. In a compliance matrix, a row is
> **an obligation the law imposes**, and the most valuable rows are the ones with **no document
> behind them**. Document-mass tools cannot generate those rows, because a corpus can only be
> asked about what is in it.

---

## 1. The compliance matrix — the India-specific equivalent of tabular review

### 1.1 What a row is

One row = one **obligation instance**: `(obligation, company, period, as_of_date)`.

Rows are generated from the **company profile**, not from the uploaded documents. A company with
no documents at all still gets a full matrix; every cell in the evidence column reads
`NO_EVIDENCE_HELD`, and that is a correct and useful output.

Row generation is deterministic — `applicability.py`'s expression evaluator decides applicability,
never a language model (`applicability.py` module docstring; `checker/assess.py` is the same
pattern for the PoSH-era rules and is the shape to reuse).

> **Known gap, flagged.** `applicability.CompanyProfile` today is PoSH-shaped
> (`employee_count`, `establishment_type`, `has_hazardous_process`, `districts`). A corporate
> profile — CIN, class, listed status, incorporation date, FY end, paid-up capital, preceding-year
> turnover, holding/subsidiary relations, previous AGM date, s.92/s.137 default flag, MSC-2
> certificate date — **does not exist yet**. This is the first build task and everything in §2
> depends on it. The evaluator itself is reusable unchanged.

### 1.2 Columns — exact specification

Grouped into six blocks. Blocks A-C render in the default table; D-F expand per row and are
included verbatim in every export.

#### Block A — identity

| Column | Type | Populated by |
|---|---|---|
| `obligation_id` | stable string, e.g. `CA13-S96-AGM-DEADLINE` | An **obligation register** (to build). One entry per duty, authored once, reviewed by a human, versioned. |
| `obligation` | one sentence, our own words | The register. **This is the original matter that carries the statutory quotation** — see §6. |
| `provision` | instrument-qualified ref, `ACT:COMPANIES_ACT_2013:S96` | `checker/legal_ref.py`. A provision number is never an identity: r.56 and s.56 are different provisions and a number-keyed lookup silently returns whichever was indexed first. |
| `depends_on` | list of `obligation_id` | `checker/provision_graph.py` — edges are quoted from the statute's own words, not authored by us. |

#### Block B — applicability

| Column | Type | Populated by |
|---|---|---|
| `applicability` | `APPLIES` / `DOES_NOT_APPLY` / `INSUFFICIENT_DATA` | `applicability.evaluate(expr, profile)`. Nothing else may write this cell. |
| `applicability_trace` | rendered boolean tree | `applicability.Trace.render()`. Shown verbatim, never summarised. A user who disagrees with the row must be able to see which leaf decided it. |
| `class_basis` | which company-class findings drove the row | The class engine (§2, F4): small / OPC / dormant / deemed-public-by-s.2(71)-proviso, each with the test and the period it was tested over. |
| `exemption_gate` | `OPEN` / `COLLAPSED` / `UNKNOWN` | para 2A of G.S.R. 464(E) as inserted by G.S.R. 583(E). One late s.92 or s.137 filing collapses the whole private-company exemption set. Default `UNKNOWN` until the default flag is supplied. |

#### Block C — temporal

| Column | Type | Populated by |
|---|---|---|
| `as_of` | date | User input. The date the row is evaluated for — a transaction date, not necessarily today. |
| `text_fidelity` | `EXACT` / `PARTIAL` / `ABSTAIN` | `checker/as_of.py` + `checker/witness_span.py`. `PARTIAL` means the amendment span could not be reversed from the source (SD-003, ten genuine unclosed spans). |
| `commencement` | instrument id + list item + sha256 | `checker/commencement.py`. A footnote w.e.f. date is **not** provenance; the notification that appointed the date is. Where they diverge, both are shown. |
| `amendment_count` | int in force at `as_of` | `checker/timeline.py` — 434 amendment records parsed from India Code's own footnotes, 431 carrying a w.e.f. date. |
| `staleness` | `FRESH` / `STALENESS_WARNING` / `STALE_TEXT` | Corpus `fetched_at` + stored-vs-current sha256 + whether the source now marks the provision omitted. `STALE_TEXT` = we hold live text for a provision the source marks omitted, i.e. serving repealed law as current. |

#### Block D — evidence

| Column | Type | Populated by |
|---|---|---|
| `evidence` | list of spans | Char offsets + quoted text from the user's own uploaded document. Never a paraphrase. `NO_EVIDENCE_HELD` where nothing matched — the most valuable value in the table. |
| `evidence_source_class` | `PRIMARY_STATUTE` / `GAZETTE` / `SUBORDINATE_RULE` / `SECRETARIAL_STANDARD` / `ROC_ORDER` / `USER_DOCUMENT` / `SECONDARY` / `NONE` | Set at ingestion, never inferred at read time. |
| `source_state` | `SERVABLE` / `UNRESOLVED` / `DEFECT_FLAGGED` | Inherited from `checker/provenance.py` via `checker/evidence_pack.py`. The four SD-002 sections (s.16, s.124, s.76A, s.329) are `UNRESOLVED` and unusable — by the general rule, not a special case. |
| `derived_date` | `{interval_text, anchor_label, anchor, result, binding_limb}` | `checker/derived_date.py` / `checker/agm.py`. The **interval** is verified verbatim against the cited provision; the result is derived, never retrieved and never generated. |
| `qualifiers` | per-qualifier `PRESERVED` / `MISSING` / `NOT_APPLICABLE` | `checker/entail_qualifier.py` inventory + `checker/review_table.py` accounting. `NOT_APPLICABLE` is deliberately hard to reach — only an explicit company-type mismatch. |

#### Block E — outcome

| Column | Type | Populated by |
|---|---|---|
| `status` | `VERIFIED` / `PARTIALLY_VERIFIED` / `UNVERIFIED` / `INAPPLICABLE` / `POTENTIAL_ISSUE` / `STALENESS_WARNING` | Derived, and **gated**: `VERIFIED` requires `applicability=APPLIES` **and** `text_fidelity=EXACT` **and** `commencement` present **and** `source_state=SERVABLE` **and** zero `MISSING` qualifiers **and** zero `missing_facts`. Same gate as `EvidenceCard.status == COMPLETE` in `checker/s96_slice.py`. |
| `finding` | `APPLICABLE_DEFECT` / `POTENTIAL_ISSUE` / `STALENESS_WARNING` / `INAPPLICABLE` / `UNVERIFIED` / `INFORMATIONAL` | The rule's own output category. A rule scoped out by document type returns `INAPPLICABLE`, never a defect — the largest failure the real-document corpus exposed (`checker/ss/defects.py`, 80-93% false positives when minutes checks ran on notices). |
| `penalty_shape` | `{kind: fine|penalty, per: meeting|book|financial_year|officer, s446B_halved: bool}` | `docs/COMPLIANCE_MECHANICS.md` §3 and `checker/ss/RULES.md`. Fines (s.99, s.129(7), s.147) are criminal and court-imposed; penalties (s.92(5), s.134(8), s.137(3), s.173(4), s.184(4), s.188(5)) are adjudicated by the Registrar under s.454. Never presented identically. |
| `missing_facts` | list | What the user must supply before the row can leave `UNVERIFIED`. Named **before** the computation is attempted (`checker/matter.missing_for_agm()`), not after the user has already been given nothing. |
| `unresolved` | list | Carried, not decided. The eight open questions in `docs/COMPLIANCE_MECHANICS.md` §4 — e.g. whether a Registrar's AGM extension displaces the fifteen-month limb. |

#### Block F — review

| Column | Type | Populated by |
|---|---|---|
| `review` | `PENDING` / `{reviewer, role, date}` | Human only. No code path sets this to anything but `PENDING`. |
| `export_hash` | sha256 of the rendered row | So a row quoted in a file note can be shown to be the row we produced. |

### 1.3 What the matrix must never do

- Emit a total, a score, a percentage or a "compliance health" figure. `checker/epistemic_status.py`
  records why at length: there is no aleatoric uncertainty to be probabilistic about, calibration
  is unreachable at n=0 labels, and the arithmetic would launder invention into something that
  reads as measurement.
- Colour a row green. `VERIFIED` means *the evidence chain is complete*, not *the company is
  compliant*. Compliance is a legal conclusion and we do not make it (`docs/NON_GOALS.md`).
- Hide a row it could not evaluate. A silently dropped row is indistinguishable from an obligation
  that does not exist — the exact failure `checker/evidence_pack.py` exists to prevent.

---

## 2. Ranked feature list

Ranked by `(value to user) / (evidence we can produce today)`. **Evidence grade** is what we can
show a sceptical practitioner *this week*, from artefacts already in this repo.

---

### F1 — The obligation matrix itself
**Rank 1. Value: highest. Evidence today: medium (engine parts exist; the register and the corporate profile do not).**

**Does:** takes a company profile and an as-of date, emits the matrix in §1. No document required.

**Pain removed:** the practitioner's real first-hour task on a new client is *"what does this
company owe, and by when"* — today done from memory, a Word checklist of unknown vintage, or a
blog post. The matrix makes the obligation set explicit and dated.

**Evidence it must show:** every column in §1.2. Nothing renders without `applicability_trace`.

**How it can be wrong:**
- The obligation register is authored by us. An obligation we never wrote down cannot appear —
  **false negatives are structural and currently unmeasured** (R-008: *"never measured — all
  corpus docs are compliant"*). This is the single largest honesty risk in the product.
- Wrong company class propagates to every row (F4).
- A row generated for a period the company did not exist in.

**Must refuse:** to state a deadline where `missing_facts` is non-empty; to render `VERIFIED`
without commencement provenance; to answer for a statute outside the Companies Act 2013.

**s.52 posture:** the matrix is original matter throughout (obligation statements, traces,
derived dates, accounting). Statutory text appears only inside an expanded row, adjacent to that
row's original matter. No column exports raw `content` alone.

---

### F2 — AGM deadline card (s.96), dated
**Rank 2. Value: high. Evidence today: HIGH — built and passing.**

**Does:** computes the AGM deadline for a financial year, names the **binding limb**, and issues an
evidence card carrying source hash, amending instrument, commencement notification, the exact
commencement list item, and the reconstructed text as of the relevant date.

**Pain removed:** the hybrid rule `MIN(FY_close + 6 months, previous_AGM + 15 months)` is where
generic calendars go wrong, because the fifteen-month limb needs state carried from last year. A
company that took a three-month Registrar extension in year N usually finds the fifteen-month limb
binds in year N+1.

**Evidence it must show:** already implemented in `checker/s96_slice.py` — `Act 1 of 2018` s.26
as the substitution witness, `S.O. 2422(E)` as the commencement instrument with its list item
quoted, both text hashes, fidelity `EXACT` on both sides of 13 June 2018, and the named binding
limb. The card refuses to render `COMPLETE` when any is missing and prints *"must not be relied
on"* in terms a reader cannot miss.

**How it can be wrong:** the previous AGM date is a user fact we do not verify; a Registrar
extension order is an input we do not hold; OPC has no s.96 deadline at all and the card must
carry none (it does); the reconstruction rests on a single source for the substituted span, and
whole-section reconstruction remains `UNVERIFIED` against any independent source
(`docs/RETRACTIONS.md`).

**Must refuse:** to decide whether a Registrar's extension displaces the fifteen-month limb —
carried in `UNRESOLVED_NOTES` and extended only on an order supplied as input. To emit a deadline
for an OPC. To compute from `PARTIAL` text.

**s.52 posture:** the card is dense original matter; the provision text sits inside it, never
alone. Compliant as built.

---

### F3 — Board-meeting regime card (s.173)
**Rank 3. Value: high. Evidence today: HIGH — built.**

**Does:** assesses board meetings for a calendar year under the correct regime: s.173(1)
**ceiling** (not more than 120 days between meetings, four meetings) vs s.173(5) **floor** (one
per half calendar year, gap **not less than** 90 days) for OPC/small/dormant.

**Pain removed:** the floor/ceiling inversion. A verifier blind to direction reports compliance
for a relaxed-regime company whose meetings were thirty days apart — turning a defect into a clean
bill of health. `checker/s173_slice.py` was built specifically to hold this distinction.

**Evidence it must show:** the regime named, the direction (`floor`/`ceiling`) on every finding,
the limit, the observed value, and the citation. Quorum is **surfaced as an open dependency on
s.174, never assumed** — the module records it rather than certifying validity on count and gap
alone.

**How it can be wrong:** "every year" in s.173(1) is undefined; s.173(5) says calendar year; SS-1
treats s.173(1) as calendar and **the Act does not say so** (`COMPLIANCE_MECHANICS` §4.3). This is
exposed as a policy switch and must never be silently picked. Company class may be wrong (F4).
Single-director OPC status is taken as given, not verified.

**Must refuse:** to certify a meeting as validly held (quorum is s.174 and is not computed here);
to assess notice periods, video-conferencing eligibility or the s.8 relaxation — deliberately not
built, each is a separate rule with its own instrument.

**s.52 posture:** findings + direction + arithmetic are original matter; the ceiling/floor phrases
are quoted short and adjacent to them.

---

### F4 — Company-class engine with the para 2A gate
**Rank 4. Value: high (it gates everything else). Evidence today: medium — the rules are documented, the profile object is not built.**

**Does:** determines, per financial year, whether the company is small / OPC / dormant / private /
public / deemed-public, and whether the private-company exemptions are open or collapsed.

**Pain removed:** four traps that are documented in `COMPLIANCE_MECHANICS` §2 and are exactly
where a generic tool is confidently wrong:
- **Small company: both limbs are conjunctive** — "or" was substituted by "and" (S.O. 504(E),
  13 Feb 2015). Turnover is tested against the **immediately preceding** year, so the two limbs
  use different periods. Status is re-tested annually; it is not sticky.
- **A private subsidiary of a public company is a public company for the whole Act**
  (s.2(71) proviso) — so not small, no MGT-7A, no abridged board report, no G.S.R. 464(E) relief.
- **para 2A gates every private-company exemption.** One late AOC-4 collapses signing relief, the
  start-up board-meeting relaxation, interested-director participation and related-party voting.
- **Dormant status is ROC-conferred**, not self-assessed — the engine must hold an MSC-2
  certificate date, not an "inactive" self-test.

**Evidence it must show:** per limb, the figure used, the period it came from, whether the
financial statement was audited, and the instrument that set the operator.

**How it can be wrong:** unaudited denominators (the rule then supplies none — return "cannot
determine", never substitute); a default flag the user reports rather than one we verify; group
structure the user describes incompletely.

**Must refuse:** to guess a default flag. To use unaudited figures as a denominator. To treat
class as sticky across years.

**s.52 posture:** the class determination is original matter; the definitional text of s.2(85) /
s.2(71) is quoted inside it.

---

### F5 — Abolished-obligation suppression
**Rank 5. Value: high and unusual — it *removes* work rather than adding warnings. Evidence today: medium-high (documented with instrument and date).**

**Does:** maintains an explicit register of obligations that **no longer exist** as of the as-of
date, and suppresses them from the matrix with an `INAPPLICABLE` row stating why.

**Pain removed:** the canonical example is **annual auditor ratification**. The first proviso to
s.139(1) was omitted by Act 1 of 2018 s.40 w.e.f. 7 May 2018. There has been no annual ratification
obligation since FY 2018-19, and generating one is described in our own source research as *the
single most common false positive in Indian compliance calendars*
(`COMPLIANCE_MECHANICS` §2). A second: RD Hyderabad (Stanley Lifestyles, hearing 24.07.2025) held
that **SS-1 was amended in 2017 to delete** the Director's Report disclosure of board-meeting
numbers/dates and attendance — a penalty on that ground was unwarranted (`checker/ss/RULES.md`).

**Evidence it must show:** the omitting/amending instrument, its clause, its commencement, and the
date range in which the obligation existed. A suppression is as much a legal assertion as a
finding and carries the same evidence burden.

**How it can be wrong:** an obligation may be omitted from the Act but re-imposed by a Rule, a
notification or a listing regulation we do not hold. Suppression is therefore narrow and must
never be phrased as "you do not need to do this" — only as "this Act provision imposed no such
duty on that date, and we hold only the Act".

**Must refuse:** to suppress on a footnote alone with no commencement instrument. To suppress
anything outside the Companies Act 2013 and the Rules we hold.

**s.52 posture:** a suppression row is entirely original matter; the omitted wording is quoted only
alongside its explanation.

---

### F6 — Secretarial Standards defect scan with exposure arithmetic
**Rank 6. Value: high for the CS-adjacent work a small practice actually does. Evidence today: HIGH on rules, LOW on false negatives.**

**Does:** deterministic SS-1/SS-2 checks over minutes, notices and outcome filings
(`checker/ss/defects.py`), each traced to a real s.454 adjudication order, plus per-meeting /
per-book / per-financial-year penalty exposure with the s.446B halving.

**Pain removed:** the corpus of 68 orders (2021-2026) shows **every defence has failed** —
voluntary disclosure, rectification before the order, "procedural lapse, no mala fide intent",
records lost to a flood. The only value available is pre-emptive, and the exposure multiplies in a
way practitioners routinely under-estimate: Trouw Nutrition ~Rs 21.35 lakh across 54 board
meetings; Om Shyamji Foods drew **three separate orders on the same day**, one per minutes book;
Rosmerta Autotech drew five.

**Evidence it must show:** rule ID, the SS clause, the ROC order cited as precedent, the observed
text, and — critically — `NEEDS_BOOK` where the check is a property of the **physical minutes
book** (consecutive pagination across the whole book, Chairman's initials on every page, blank
pages scored out). Those cannot be decided from a .docx and reporting them as `PASS` would be the
failure mode this product exists to prevent.

**How it can be wrong:**
- **Over-firing by document type.** Already observed at 80-93% false positives when minutes checks
  ran against notices. Gating exists; R-003 records T1.4a/T1.6a/b/c/T1.7 as **still over-firing**.
- **False negatives are unmeasured.** Every document in `corpus/testdocs/` is compliant (R-008).
  We hold **zero** minutes books and zero deliberately-defective documents. B-001 is the critical
  path.
- Version drift: a check firing against a repealed SS requirement is the Stanley Lifestyles error.
  Every check must carry the SS version and the date range it is valid for.

**Must refuse:** to fire as penalty-backed any rule with **zero** enforcement precedent. Named in
`RULES.md`: route map / venue particulars in an AGM notice (zero orders), failure to record leave
of absence (zero), failure to record dissent (zero as a charged defect), AGM notice as a numeric
day-count shortfall (essentially zero — the two s.101 orders are "no notice at all" and "oral
notice"). These may appear only as clearly-labelled advisory. It must also refuse to claim "high
enforcement risk" — SS orders are ~4% of published adjudication orders; filing defaults dominate
at 16.2%.

**s.52 posture:** SS-1/SS-2 are ICSI text, **not** Act text, and s.52(1)(q)(ii) does not cover
them — quote sparingly under fair dealing with attribution, or cite clause numbers without
reproducing. Statutory hooks (s.118(10), s.118(11), s.446B) are quoted inside the finding.

---

### F7 — Precedent drift audit ("does your template still match the law on date D")
**Rank 7. Value: potentially the highest of all; it is the ComplyRelax fork problem stated as a feature. Evidence today: LOW-MEDIUM — no user templates held, and no measured detection.**

**Does:** the user uploads their own Word precedent (board notice, AGM notice, resolution,
minutes shell). We report which statutory hooks it relies on, what the law said when the template
appears to have been written, what it says on the target date, and which sentences are now
`STALENESS_WARNING`.

**Pain removed:** stated in `CLAUDE.md` — ComplyRelax's own instruction PDFs say customising a
template stops legal updates and editing a variable stops company-data linking. Every real firm's
documents are a **private fork drifting from both the law and its data**, unreachable by any
vendor update including a competitor's. The defect is detectable only at the output. That is the
whole thesis of an audit layer, and this feature is the thesis made touchable.

**Evidence it must show:** per flagged sentence, the provision it maps to, the instrument that
changed it, the commencement, and the two texts. Where the mapping is a guess, `UNVERIFIED`.

**How it can be wrong:** mapping free-text sentences to provisions is the least evidenced step in
the whole system; a template may deliberately exceed the statutory minimum (a stricter clause is
not a defect); "written on date X" is inferred, not known.

**Must refuse:** to rewrite the template. To say a clause is wrong — only that a provision it
appears to rely on changed on a stated date. To assert a mapping below the grounding threshold.

**s.52 posture:** output is dominated by the user's own document plus our commentary; statutory
text appears as short adjacent quotations. Low risk **provided** no "show me the full section"
affordance exists without the card.

---

### F8 — Commencement provenance card
**Rank 8. Value: medium-high, and structurally unique to us. Evidence today: HIGH — built.**

**Does:** for a given amendment, names the notification that actually appointed the date, quotes
the exact list item, hashes it, and **reports divergence** where India Code's footnote date is not
supported by any notification we hold.

**Pain removed:** the practitioner asking "was this in force on the transaction date" currently
trusts a footnote. `checker/commencement.py` documents a real divergence: S.O. 1833(E) of 7 May
2018 brings s.31 of the amending Act into force and does **not** mention s.51 (which amends
s.161) — yet India Code's footnote gives s.161's amendment the same 7 May 2018 date.

**Evidence it must show:** the instrument identifier, Gazette number where held, the list item
verbatim, the sha256, and an explicit `NOT SUPPORTED BY A NOTIFICATION WE HOLD` where absent.

**How it can be wrong:** our notification holdings are incomplete; absence of a notification in our
store is not absence in the Gazette, and the wording must say so.

**Must refuse:** to treat a footnote date as provenance. To infer a commencement from a
neighbouring section's date.

**s.52 posture:** **Gazette matter is clean under s.52(1)(q)(i)**, so the notification text is the
one thing we may serve more freely. Prefer the gazetted instrument wherever one exists — this is
a real design lever, not a footnote.

---

### F9 — Dated provision reading, with commentary
**Rank 9. Value: high demand, but constrained by copyright. Evidence today: HIGH for the mechanism, and the constraint is the design.**

**Does:** answers "what did s.96 say on 12 June 2018, and what changed the next day" — as a
**reading card**, never as a browser. Text is served only inside our commentary: the fidelity, the
witness instrument, the commencement, the qualifier inventory and the practical consequence.

**Pain removed:** retrospective review at a transaction date, which is the corporate lawyer's
recurring problem and which no consolidation answers.

**Evidence it must show:** fidelity `EXACT` / `PARTIAL` / `ABSTAIN` and the basis sentence
(`"the span boundary is stated by Act 1 of 2018 s.26, not inferred"`). Where `PARTIAL`, say plainly
that the prior wording cannot be reconstructed from this source and why (SD-003).

**How it can be wrong:** roughly two thirds of amended sections cannot be reconstructed exactly
from India Code alone; whole-section point-in-time reconstruction is `UNVERIFIED` against any
external source; the only corroboration is span-level — 24 amended spans matched against the
amending Acts on Indian Kanoon with 0 conflicts (`docs/CORROBORATION.md`), which corroborates
spans, **not** sections. That distinction is exactly what the retracted claims missed.

**Must refuse:** to render a full clean section. To offer download, copy-all, or an API field
containing only `content`. To reconstruct where `text_fidelity` is `PARTIAL` without saying so on
the same screen.

**s.52 posture:** **the highest-risk feature in the plan.** Act text may only ever be served
together with original matter, so this is buildable *only* as a card. Never a statute browser,
never a side-by-side diff of two clean texts, never an Act download
(`docs/PLAN_REVIEW_KIMI_2026_08_22.md` records the same feature being blocked once already;
`scripts/preflight.py` enforces it). **Open and UNVERIFIED:** whether machine-generated commentary
satisfies (q)(ii) at all is a counsel question, already logged as human-gated. Until it is
answered, the commentary on every card must be substantial and specific to the query, not a
boilerplate wrapper.

---

### F10 — Qualifier-preservation check on the user's own sentence
**Rank 10. Value: medium-high, distinctive. Evidence today: medium-high — the machinery is built.**

**Does:** the user pastes a sentence they are about to put in an advice note or a board note. We
report every material qualifier the provision attaches, and whether the sentence preserves it —
`PRESERVED` / `MISSING` / `NOT_APPLICABLE`.

**Pain removed:** the sentence that is true of most companies and wrong for this one. From
`checker/grounding_policy.py`: *"A private company's meeting is quorate when two members attend"*
is right for most and wrong for any whose articles require more — s.103(1) opens with exactly that
carve-out. The citation was genuine; the conclusion was misleading. That gap **is** the product.

**Evidence it must show:** each qualifier quoted from the provision, with its trigger phrase, and
the accounting state. `NOT_APPLICABLE` fires only on an explicit company-type mismatch.

**How it can be wrong:** the qualifier inventory is hand-built and incomplete; SD-004 proves
phrase-matching misses real qualifiers — `as may be prescribed` does not match s.101(1) because
India Code serves `maybe`, so a qualifier present in law is invisible to that pattern.

**Must refuse:** to rewrite the user's sentence. To report `PRESERVED` for a provision whose
inventory has not been human-reviewed.

**s.52 posture:** quotations are short, qualifier-length, and each is immediately followed by our
accounting. Low risk.

---

### F11 — Source-defect disclosure
**Rank 11. Value: medium — trust-building, and nobody else does it. Evidence today: HIGH.**

**Does:** wherever a row touches a provision with a known source defect, says so inline: SD-001
(the editorial instruction "To be deleted" left inside India Code's s.1), SD-002 (vintage
divergence on s.16, s.124, s.76A, s.329 — held `UNRESOLVED` and **unservable**), SD-003 (ten
genuine unclosed spans, s.96 among them), SD-004 (`hall` for `shall` in s.174(1); `maybe` for
`may be` in s.101(1), both preserved verbatim).

**Pain removed:** a practitioner who copies statutory text into a filing needs to know the served
text has a transcription error in it. No competitor tells them, because most do not know.

**Evidence it must show:** the served text verbatim, the defect class, when we found it, and that
we did not repair it.

**How it can be wrong:** our defect list is the defects we happen to have found; SD-003 taught the
lesson recorded in that file — *counting instances is not diagnosis*; 42 of 121 "source defects"
turned out to be our own regex.

**Must refuse:** to repair. To normalise `hall` to `shall`. A harmless instance is not an
exception to the rule.

**s.52 posture:** the defect note is original matter; the defective span is quoted precisely
because the note is about it.

---

### F12 — Carry-forward company state
**Rank 12. Value: medium (it is F2's dependency). Evidence today: medium.**

**Does:** persists `previous_agm_date`, class determinations per year, s.92/s.137 default history,
MSC-2 date, and prior findings — so year N+1 can be computed at all.

**Pain removed:** the fifteen-month limb, the annual re-test of small-company status, and the
para 2A gate all need last year's facts. Without state, the tool is a calculator; with it, it is a
register.

**How it can be wrong:** user-entered history is not verified; a correction to year N must
invalidate every downstream row rather than silently leaving them.

**Must refuse:** to carry a fact forward past a correction without re-deriving. To infer last
year's AGM date from a filing we have not read.

**s.52 posture:** no statutory text. Not applicable.

---

### F13 — Document authenticity check
**Rank 13. Value: medium, narrow. Evidence today: HIGH — built (`scripts/verify_document.py`, `checker/pdf_signature.py`).**

**Does:** cryptographic signature verification on a downloaded PDF against CCA India roots — is
this document actually what it claims to be.

**Pain removed:** small practices receive PDFs by email and WhatsApp from clients and from
portals. Nothing else in their stack tells them whether the signature is intact.

**How it can be wrong:** a valid signature says who signed and that bytes are unaltered — it says
nothing about the content being legally correct. The UI must not let the two be confused.

**Must refuse:** to treat signature validity as any kind of compliance finding.

**s.52 posture:** no Act text. Not applicable.

---

### F14 — The abstention register
**Rank 14. Value: medium, and it is the honesty surface. Evidence today: HIGH — built for the PoSH case, and the pattern generalises.**

**Does:** where we will not answer, says so — and where possible names the authority who holds the
answer, so the refusal ends in an action rather than a shrug.

**Pain removed:** `checker/register.py` records the design: *a date exists in the register only
alongside the words it came from*, and there is no code path producing one without its source. The
PoSH annual-return case shows the shape — every source on the Indian internet says 31 January, the
Rules prescribe nothing, and at least one District Officer has notified 28 February, so the honest
answer names the officer and their email instead of a plausible date.

**Corporate-law equivalents, drawn from `COMPLIANCE_MECHANICS` §4 (all currently unresolved):**
whether a Registrar's AGM extension displaces the fifteen-month limb; the OPC annual-return
deadline (s.92(4) has no OPC limb and s.96 does not apply, so no "should have been held" date
exists); "every year" in s.173(1); s.134(4) vs Rule 8A for the OPC board report; Rule 15(2)
presence vs G.S.R. 464(E) Sl.13 participation; Rule 15(3) aggregation scope; whether s.129(3) still
reaches associates and JVs after Act 1 of 2018 s.33; the first-auditor ADT-1 question.

**How it can be wrong:** an abstention on a question that is in fact settled is a real cost to the
user. Each entry needs a named resolver and a review date, or the register becomes an excuse.

**Must refuse:** to fill a blank row with a plausible date. Ever.

**s.52 posture:** no statutory text beyond the short provision phrase the abstention is about.

---

## 3. Features possible only because of the temporal / statutory work

This is the differentiation section, and it must be rigorous rather than flattering.

**The architectural claim.** A contract has an execution date and an effective date. Its clauses do
not commence in stages by government notification; no instrument retrospectively amends the text of
a signed contract; no publisher sits between the parties and the words with an editing process that
can introduce defects. So a contract-review architecture models **document versioning** — which
draft is this — and has no reason to model **norm versioning** — which law was in force. The
features below all require norm versioning with instrument-level provenance.

*(This is an inference from architecture, not a test of any product. No competitor product has
been used. **UNVERIFIED.**)*

### D1 — Retrospective review at the transaction date
"Was this board resolution good law when it was passed on 15 March 2024?" needs the provision text
as it stood on that date **with a witness for the boundary**, not a version label. We can do this
where `text_fidelity=EXACT`: boundary behaviour is proved on s.177, s.447 and s.35 — 6/6
boundaries, text changing across each, effective dates inclusive (`docs/TEMPORAL_PROOF.md`), and
s.96's pre-13-6-2018 gap is closed by Act 1 of 2018 s.26 plus S.O. 2422(E). **Honest limit:** 83
sections are `EXACT` on both sides of their first amendment; roughly two thirds of amended sections
are not, and whole-section reconstruction is `UNVERIFIED` against any independent source.

### D2 — Footnote-vs-notification divergence
Reporting that a stated w.e.f. date is **not supported by any commencement notification we hold**
(the S.O. 1833(E) / s.161 case). This requires holding the notifications as instruments and
matching their list items to amending-Act clauses. There is no analogue in contract review because
there is no external instrument that appoints when a clause starts to bite.

### D3 — Abolished-obligation suppression (F5)
Structurally impossible for a playbook-diff architecture. A playbook is a snapshot of a house
position with no commencement metadata; it can tell you a document differs from the house position,
never that the house position was itself repealed on 7 May 2018.

### D4 — Operator drift inside a subordinate rule
Rule 15(3) clause (a) items (i)-(iv) became `>=` ("ten per cent or more") by G.S.R. 309(E) of
30 Mar 2017; clauses (b) and (c) remain strictly `>`. A single character, in a Rule, with a
commencement date, changing an eligibility test. Detecting it requires a dated corpus of
subordinate legislation at clause granularity.

### D5 — Mid-year threshold changes and split financial years
G.S.R. 857(E) of 18 Nov 2019 removed Rule 15(3)'s rupee caps mid-year. FY 2019-20 must be split:
transactions before that date use the capped test, from that date the uncapped. **Each transaction
must be date-stamped and evaluated individually; batching by year is wrong.** No document-mass tool
does this, because nothing about a contract corpus suggests the applicable test changes partway
through the period being reviewed.

### D6 — Conjunctive/disjunctive substitution
"or" substituted by "and" in the small-company definition (S.O. 504(E), 13 Feb 2015), turning a
disjunctive eligibility test into a conjunctive one, with the two limbs measured over **different**
periods. Reachable only from a dated statutory corpus.

### D7 — Version-dated compliance standards
Every SS check carries the standard version and the date range it is valid for, because RD
Hyderabad held (Stanley Lifestyles, 24.07.2025) that SS-1's 2017 amendment deleted a requirement a
penalty had been imposed under. A check firing against a repealed standard is the same failure this
product exists to prevent.

### D8 — Repealed-text detection (`STALE_TEXT`)
The checker reports when we hold live text for a provision the source marks omitted — i.e. serving
repealed law as current. Meaningful only against a corpus that knows about omissions (43 index
entries resolve to `None` by design: s.11; ss.253-269 omitted by the IBC w.e.f. 15-11-2016).

### D9 — Publisher-defect provenance
Knowing *which* spans cannot be reconstructed lets us abstain precisely rather than guess.
`_find_span` carries the record of an earlier attempt to swallow to end-of-document: it captured
8,777 characters in s.1323 and destroyed a later marker. Guessing a span end is a legal judgement
disguised as a parsing decision.

### D10 — Instrument-qualified identity
`ACT:COMPANIES_ACT_2013:S56` and `RULE:MEETINGS_OF_BOARD_2014:R56` are different provisions with
the same number, in the same PDF. A number-keyed lookup returns whichever was indexed first — a
wrong legal answer at full confidence. Contract review has no equivalent collision because clause
numbering is local to the document being read.

### Where the differentiation is weaker than it looks — state this plainly
- A frontier model with web access can often *state* an amendment date correctly. What it cannot
  do is show the notification list item, the source hash, and the reconstruction fidelity. Our
  advantage is **auditability**, not knowledge.
- Indian commercial publishers (SCC Online, Taxmann) hold better-curated historical text than we
  do. We are not out-researching them; we are the only ones exposing provenance and defects
  machine-readably. *(Their internal capabilities are **UNVERIFIED** — we hold no subscription and
  their terms prohibit systematic download.)*
- None of D1-D10 is worth anything until B-001 exists. Differentiation asserted without a benchmark
  is a claim, not a moat.

---

## 4. Features not to build, and why

| Not building | Reason |
|---|---|
| **Clean-statute browser, Act download, side-by-side clean-text diff** | s.52(1)(q)(ii). Act text is servable only together with original matter. Already blocked once (`PLAN_REVIEW_KIMI_2026_08_22.md`); enforced by `scripts/preflight.py`. |
| **Document generator** | ComplyRelax is free to ICSI members until 31 Mar 2029 and has shipped 201 unbroken updates Oct 2020 - Aug 2026. Generation is commoditised; the audit layer is not. |
| **"Legally compliant" certification** | A legal conclusion. `docs/NON_GOALS.md`. |
| **Compliance score / risk percentage / maturity number** | `checker/epistemic_status.py`: no aleatoric uncertainty to model, calibration unreachable at zero labels, and the arithmetic launders invention into something that reads as measurement. |
| **Case-law citations** | We hold **zero** judgments. A fabricated citation carried into a filing ends the customer's credibility with a judge and ours with the profession. Say "we hold statute only" — that sentence is itself the differentiator. |
| **Penalty-backed findings with no enforcement precedent** | Route map in an AGM notice, leave of absence, dissent, numeric day-count shortfall — all **zero** orders across 1,609 tagged. Advisory only, labelled. |
| **Automatic MCA filing** | Transfers liability to us and depends on a portal we do not control. |
| **Vault / data-room / document-mass features** | The user has no document mass. Building for an asset the customer does not own is the whole mistake this plan exists to avoid. |
| **Firm playbook diff** | A solo practice has no playbook. Its "playbook" is a drifting Word template, which is F7 and a different feature. |
| **Vector search** | ~470 sections. BM25 wins on entity-rich exact match at this size (Sciavolino et al., EMNLP 2021). |
| **General legal chatbot / "chat with the Act"** | Puts us against every frontier model and abandons the wedge. Also the fastest route to serving bare statutory text. |
| **Neo4j / Pinecone / Elasticsearch / Celery** | Repo has zero third-party dependencies. At the current user count these add five failure modes and no measurable latency win. |
| **Generic deadline calendar with push alerts** | Only where the date is statute-fixed **and** evidenced. A confidently wrong reminder is worse than none, and this is exactly where auditor-ratification-style false positives are generated. |
| **Scraping MCA / paid publishers / user-agent rotation** | `CLAUDE.md` source policy. Explicitly rejected once already. |
| **Fine-tuning or a foundation model** | No data rights, no budget, not the moat. |
| **OCR intake** | **Not "never" — "not yet", and flagged as a risk.** Every document in `corpus/testdocs/` is text-extractable, so OCR quality is currently untested. Real small-practice intake is likely scan-heavy. **UNVERIFIED**; would be settled by collecting 20 documents as they actually arrive at a practice. |

---

## 5. Distribution — where does this user actually work?

### 5.1 What we honestly know

Almost nothing, and the repo says so. **Marked UNVERIFIED in full.**

- Four interviews have been conducted, all with lawyers, none with a Company Secretary
  (`docs/PRODUCT_SCOPE.md`). Four is not a sample.
- The market model is built on ICSI Certificate-of-Practice counts and CS pricing anchors, and is
  **scoped to a secondary segment pending a rebuild** (R-011). No figure in it may be used
  externally.
- R-007 (current CoP figure) and R-009 (whether RBI e-mandate supports annual auto-renewal) are
  open. H-004 (Reddit OAuth) is described as *the only route to a live practitioner voice* and is
  unfulfilled.
- Nothing in this repository records **where** an Indian corporate practitioner does this work —
  which application, which device, which file format, at what hour.

Anything below this line is reasoning, not evidence.

### 5.2 Reasoned candidates, with the evidence each would need

| Surface | Argument for | Argument against | Status |
|---|---|---|---|
| **Browser app, upload PDF/DOCX, printable evidence card** | Zero install; the output is a card a partner reads and a file note quotes; we already emit print-ready HTML with correct `@page` rules and no system dependencies (`checker/documents.py`). | Requires leaving the drafting tool. | **Recommended first surface.** Lowest build cost, and it is the only surface whose enabling work is already done. |
| **MS Word add-in** | If drafting happens in Word desktop, the audit belongs where the text is. | Whether Indian small practices use Word desktop vs Google Docs vs LibreOffice is **completely unverified**; add-in distribution is a separate build and review cycle. | Defer until observed. |
| **Email-in / digest** | Documents already arrive by email; no new habit. | Attachment handling, and a wrong answer sent by email cannot be corrected in place. | Second. |
| **WhatsApp** | Plausibly where Indian client documents actually move. | Confidentiality, no audit trail, terrible surface for a dense evidence card. **UNVERIFIED and probably a trap.** | No. |
| **API / integration with an Indian practice-management tool** | Meets the user inside existing workflow. | Requires a partner, and we have not identified one. | Later. |

### 5.3 The honest position

The delivery surface is **not decided by taste**. The output is a dense evidence card with hashes,
instrument names and an abstention block. That format demands a screen and a print path, not a chat
bubble — which points at the browser app, and that is the recommendation. But **which** browser,
whose laptop, and at what point in the workflow are unknown.

### 5.4 What would settle it

1. **B-001** — the 30-50 document benchmark including deliberately defective documents. It settles
   whether the product works at all, which precedes any distribution question. Critical path.
2. **Ten to fifteen practitioners, observed rather than asked**, using the four behavioural
   questions in `docs/EVIDENCE_PROTOCOL.md`: what did you check first on the last document you
   reviewed; how do you currently check what the law was on the relevant date; what would you need
   to see before trusting an automated finding; what do you still do manually after using your
   current tools. Record role and PQE on every data point; never present student feedback as lawyer
   validation.
3. **One collection exercise**: 20 documents in the format they actually arrive in. Settles the OCR
   question and the file-format question in a single week.
4. **H-001** — expert review by one or two practising corporate lawyers. Gates claims, not
   development.

Until 1 and 2 exist, every sentence in this section stays labelled UNVERIFIED, and no distribution
spend is justified.

---

## 6. s.52(1)(q)(ii) posture — consolidated

### The rule as it binds this product

Act text may only ever be served **together with original matter**. Never emit bare statutory text.
Never build a clean-statute browser or an Act download. Gazette matter is clean under (q)(i), so
prefer the gazetted instrument wherever one exists. Attribute Indian Kanoon prominently where it is
used as a fallback source.

**Open and UNVERIFIED:** whether *machine-generated* commentary satisfies (q)(ii). This is a
counsel question already logged as human-gated, and it is not answered here. Until it is answered,
the operating assumption is the conservative one — commentary must be substantial, specific to the
query, and not a boilerplate wrapper generated to satisfy a rule.

### Enforcement, not intention

Three mechanical constraints, so posture is a property of the system rather than a promise:

1. **No API field ever returns `content` alone.** Every response carrying provision text carries
   the card that surrounds it. `checker/evidence_pack.py` is already the single boundary through
   which provision text reaches a model; the same boundary governs what reaches a user.
2. **No export path without the card.** No copy-all, no "download section", no print view that
   strips the commentary. `scripts/preflight.py` already guards this.
3. **Ratio check at render time.** A rendered view whose quoted-statute character count exceeds its
   original-matter character count fails to render. Crude, and crude is the point — it cannot be
   argued with.

### Per-feature posture

| # | Feature | Act text shown? | Original matter accompanying it |
|---|---|---|---|
| F1 | Obligation matrix | Only inside an expanded row | Obligation statement, applicability trace, derived date, qualifier accounting, penalty shape, missing facts, unresolved list |
| F2 | AGM deadline card (s.96) | Yes, inside the card | Full evidence card: hashes, witness instrument, commencement list item, binding limb, constraints, unresolved notes |
| F3 | Board regime card (s.173) | Short quotes only ("not more than", "not less than") | Regime, direction, limit, observed, quorum dependency, open questions |
| F4 | Company-class engine | Definitional text of s.2(85)/s.2(71) | Per-limb figures, periods, audited flag, operator instrument, exemption gate |
| F5 | Abolished-obligation suppression | Omitted wording, quoted to explain the omission | Omitting instrument, clause, commencement, date range in which the duty existed |
| F6 | SS defect scan | s.118(10)/(11), s.446B only. **SS-1/SS-2 are ICSI text, not Act text — s.52(1)(q)(ii) does not cover them.** Cite clause numbers; quote sparingly with attribution | Rule ID, ROC order, observed text, exposure arithmetic, `NEEDS_BOOK` scope note |
| F7 | Precedent drift audit | Short adjacent quotations | The user's own document dominates; plus mapping, instrument, commencement, both dates |
| F8 | Commencement provenance | **Gazette text — clean under (q)(i)** | Divergence analysis, hash, list item, "not supported by any notification we hold" |
| F9 | Dated provision reading | Yes — **highest risk in the plan** | Fidelity, basis sentence, witness, commencement, qualifier inventory, consequence. Card only. Never a browser, diff, or download |
| F10 | Qualifier check | Qualifier-length quotations | Per-qualifier accounting against the user's sentence |
| F11 | Source-defect disclosure | The defective span, verbatim | The defect note is entirely about that span; class, discovery date, non-repair statement |
| F12 | Carry-forward state | None | N/A |
| F13 | Document authenticity | None | N/A |
| F14 | Abstention register | Short provision phrase only | The abstention, its reason, the named resolver |

---

## 7. Build order, and what gates what

| Order | Item | Gated by |
|---|---|---|
| 0 | **B-001 benchmark, including deliberately defective documents** | Nothing. Critical path. Every claim below is unassertable without it. |
| 1 | Corporate `CompanyProfile` + obligation register schema | Nothing. Blocks F1, F4, F5, F12. |
| 2 | F4 company-class engine (para 2A gate, conjunctive small-company test) | 1 |
| 3 | F1 matrix assembly over the existing F2/F3 cards | 1, 2 |
| 4 | F5 abolished-obligation suppression | 1; needs the same commencement machinery as F8 |
| 5 | F6 SS scan rework — R-003 over-firing, R-008 false negatives | 0 |
| 6 | F8, F9, F10, F11 as row expansions | 3 |
| 7 | F7 precedent drift | 3; and the mapping step needs its own measurement |
| 8 | F12, F13, F14 | 3 |

**Standing blockers to record honestly:** R-003 (rules still over-firing), R-008 (false negatives
never measured), B-001 (no defective-document corpus), S-001 (SD-004 has no independent witness),
R-011 (market model is for the wrong segment), H-001 (no practising-lawyer review). None of them
stops building. All of them stop claiming.
