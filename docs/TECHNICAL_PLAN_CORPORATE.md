# Technical Plan — Corporate and financial compliance engine

Companies Act, 2013. Written 2026-08-15. Companion to
`../placedon-law-research/docs/BUSINESS_PLAN_CORPORATE.md`.

The architectural conclusions in `ARCHITECTURE.md` stand unchanged: **the model never decides what
the law requires**, the verifier rejects any claim absent from source, status is **ordinal** and
there is no confidence float. This document covers what is added — and **one thing that genuinely
breaks** and must be solved before a single date ships.

---

## 0. The problem that has to be solved first

**A due date is a number that does not appear in the statute.**

s.96 requires an AGM *"within six months from the date of closing of the financial year."* For a
company whose financial year closed 31 March 2026, the answer is **30 September 2026**.

Search the Act for "30 September 2026". It is not there, and it cannot be — the Act is not written
per company.

Now read the rule `verifier.py` enforces today: **reject any answer containing a figure absent from
the source text.**

> **As it stands, the verifier would reject every correct deadline this product computes, as a
> fabrication.** And relaxing the rule to let dates through deletes the mechanism the entire product
> rests on.

This is the central design question of the corporate scope. Getting it wrong in either direction
destroys something: relax the verifier and fabricated dates ship; keep it unchanged and nothing
ships.

### Resolution — verify the interval, not the result

A deadline is not an atomic claim. It is **arithmetic** over three inputs, each independently
checkable:

```
  anchor      2026-03-31          <- a FACT the user supplied (their financial year end)
  interval    "six months"        <- MUST appear verbatim in the cited provision
  operation   from the date of closing of the financial year   <- the provision's own words
  ──────────────────────────────
  result      2026-09-30          <- DERIVED. Never retrieved. Never generated.
```

A new claim type carries its own derivation:

```python
@dataclass(frozen=True)
class DerivedDate:
    result: date              # 2026-09-30
    anchor: date              # 2026-03-31, supplied by the user
    anchor_label: str         # "close of the financial year"
    interval_text: str        # "six months" — verbatim from the provision
    interval: relativedelta   # parsed; must re-derive from interval_text
    citation: str             # "s.96(1), Companies Act 2013"
    quote: str                # the provision's sentence, verbatim
```

**The verifier's new rule.** A `DerivedDate` is admissible **iff**:

1. `interval_text` appears **verbatim** in the text of the cited provision, and
2. re-running the arithmetic on `(anchor, interval)` reproduces `result` **exactly**.

The date is never sought in the source, because it is not a claim about the source — it is a claim
about arithmetic *performed on* the source.

**What the user is shown is the derivation, not just the answer:**

> **30 September 2026.**
> Your financial year closed **31 March 2026**. s.96(1) requires the meeting *"within six months
> from the date of closing of the financial year"*. Six months from 31 March 2026.

Checkable by hand in five seconds — the standard the rest of this repository holds.

**This narrows the ratchet rather than weakening it.** A model emitting a bare date still fails.
Only a date arriving with a verified interval and reproducible arithmetic passes.

---

## 1. `checker/deadlines.py` — new

Pure functions. No model, no network. Same shape as `distress.py`: deterministic, self-testing,
runnable directly.

```python
def compute(rule: DeadlineRule, facts: CompanyFacts) -> DerivedDate | Abstention
def applicable(rule: DeadlineRule, facts: CompanyFacts) -> bool
def calendar(facts: CompanyFacts, on: date) -> list[DerivedDate]   # all obligations, ordered
```

**Rules are data extracted from provisions, never hand-typed:**

| Rule | Provision | Anchor | Interval |
|---|---|---|---|
| AGM | s.96(1) | close of financial year | six months |
| AGM — maximum gap | s.96(1) proviso | previous AGM | fifteen months |
| **First AGM** | s.96(1) proviso | **incorporation** | **nine months** |
| Annual return | s.92(4) | **date of AGM** | sixty days |
| Financial statements | s.137(1) | **date of AGM** | thirty days |
| Board meetings | s.173(1) | previous meeting | one hundred and twenty days |
| Charge registration | s.77(1) | creation of charge | thirty days |
| Auditor appointment (casual vacancy) | s.139(8) | vacancy | thirty days |

**Every `interval_text` above must resolve verbatim in the ingested provision, or the rule is
refused at load time** — raising, exactly as `register.py` raises on a `DATE_NOTIFIED` with no
`reply_verbatim`. A rule that cannot find its own words in the statute is not a rule, it is a guess.

### Traps, named now because they will otherwise ship

- **First AGM is a different rule.** Nine months from incorporation, not six from financial year
  close. Applying the general rule to a first-year company is wrong in the direction that costs a
  penalty.
- **Three AGM constraints bind simultaneously** — six months from FY close, fifteen months from the
  last AGM, nine months from incorporation in year one. The operative date is the **earliest**, and
  `conflicts()` must **report the disagreement** rather than silently returning the minimum. This is
  the same failure `ARCHITECTURE.md` §3 describes: weakest-link composition is monotone, so it
  resolves disagreement into silence, and the disagreement is what the reader most needs.
- **s.92 and s.137 anchor to the AGM's *actual* date, not its due date.** An AGM held early moves
  both filing deadlines earlier. Anchoring to the deadline is a silent off-by-weeks error.
- **Extensions exist.** The Registrar may extend the AGM by up to three months on application. The
  product reports the statutory date and quotes the extension provision — it must not present the
  base date as immovable.
- **"Financial year" is defined** at s.2(41) and ordinarily ends 31 March. Read it; do not assume.

## 2. Applicability — extending `applicability.py`

Corporate obligations turn on **thresholds**, which is what the module already does for a
ten-employee test. New inputs:

```python
@dataclass(frozen=True)
class CompanyFacts:
    incorporated_on: date
    financial_year_end: date          # s.2(41)
    paid_up_capital: int              # rupees
    turnover: int                     # rupees
    borrowings: int
    net_worth: int
    net_profit: int                   # s.135 CSR threshold
    is_public: bool
    is_one_person_company: bool       # s.2(62)
    last_agm: date | None
    last_board_meeting: date | None
    number_of_members: int
```

### Where the facts come from — verified 2026-08-16

**Most of `CompanyFacts` can be fetched free, structured, from the Government.** Confirmed by direct
API call, not by report:

```
GET api.data.gov.in/resource/4dbe5667-7b6b-41d7-82af-211562424d9a
  status  ok        total  3,674,314 companies        updated  2026-07-22
```

Ministry of Corporate Affairs, published on the Open Government Data platform. Fields returned map
almost exactly onto what the applicability engine needs:

| `CompanyFacts` field | OGD field | Free? |
|---|---|---|
| `incorporated_on` | `CompanyRegistrationdate_date` | **yes** |
| `paid_up_capital` | `PaidupCapital` | **yes** |
| authorised capital | `AuthorizedCapital` | **yes** |
| `is_public` | `CompanyClass` | **yes** |
| OPC / small company category | `CompanyCategory`, `CompanySubCategory` | **yes** |
| listed-company obligations | `Listingstatus` | **yes** |
| active / struck off | `CompanyStatus` | **yes** |
| jurisdiction | `CompanyROCcode`, `CompanyStateCode` | **yes** |
| `turnover`, `net_worth`, `net_profit` | — | **user supplies** |
| `last_agm`, `last_board_meeting` | — | **user supplies** |
| **directors** | — | **the one real gap** |

**A fetched government field is a citation.** It has provenance, an update date, and no inference
step. An LLM-extracted figure is an assertion dressed as a citation. **Structured fetch is not a
compromise on the architecture — it is the stricter reading of the rule this project already set:
the model never decides a fact.**

### And this is why document parsing is not built

A proposed "document intelligence" pipeline would parse MOA/AOA and board minutes. Research
established it is the wrong call on four independent grounds:

1. **Cost.** MCA *View Public Documents* is **₹100 per company** for a 3-hour window. ₹5,000/month
   buys **50 companies of raw PDF** and nothing else. The same companies' master data is **₹0**.
2. **Accuracy ceiling.** [BuDDIE](https://arxiv.org/html/2404.04003v1) — the closest analogue,
   corporate registration filings, **born-digital** — caps at **89.97% F1** with a purpose-built
   model; **GPT-4 reaches 77.76%**. On real scans it is worse:
   [Devanagari OCR](https://arxiv.org/abs/2606.29213) collapses from chrF++ 91–98 clean to a
   **76-point spread** on real scans, and [Real5-OmniDocBench](https://arxiv.org/html/2603.04205v1)
   shows structured pipelines falling from 84.68 to **37.98 under skew alone** — with **tables** the
   most fragile element, which is the format of every capital and director schedule.
3. **No prior art.** **No dataset, benchmark or published evaluation exists** for extraction from
   Indian MOA/AOA, board minutes or MCA filings. Indian legal NLP is entirely court-judgment work.
   We would ship compliance output with no way to know whether the extractor is at 60% or 90%.
4. **It fails silently.** Stanford RegLab measured purpose-built commercial legal AI at **17–33%**
   hallucination. The failure literature calls it *"locally plausible fabrication"* — confident,
   well-formed, professionally credible, and wrong. **A compliance engine silently wrong one time in
   ten manufactures false assurance**, which is worse than no engine.

**Decision: fetch structured, do not parse.** Document parsing is reserved for genuinely
unstructured residue (a specific MOA object clause), scoped narrowly, paid for deliberately, with a
human in the loop, and **surfaced as unverified with its source page cited — never as a determined
fact.**

### Spot-check performed 2026-08-16 — results

| Test | Result |
|---|---|
| Resource responds | **yes** — `status ok`, 3,674,314 records, updated 2026-07-22 |
| Registration dates parseable | **10/10**, single ISO format `%Y-%m-%d`. No format zoo. |
| **Lookup by CIN** — the production use case | **works**: `filters[CIN]=…` returns `count=1` |
| `CompanyClass` gives the s.2(62) gate directly | **yes** — values include `One Person Company`, `Private` |
| Capital fields numeric | 9/10; empties present |
| Demo key throughput | **10 records regardless of `limit`** — a personal key is required |

**Three rules for the fetcher, each from something the spot-check found:**

1. **Filter on CIN validity at ingest.** The dataset **mixes companies and LLPs**. One sampled row
   was `ABD-0345` / *"Titan Winners Fund Management LLP"* — a valid **LLPIN**, not a CIN. LLPs are
   governed by the **LLP Act 2008**, not the Companies Act, so they are out of scope and their
   company fields are empty. Regex the 21-character CIN form; reject anything else as
   *out of scope*, not as *bad data*.

2. **An empty field means abstain, never guess.** Records with blank `PaidupCapital`,
   `CompanyClass` or `Listingstatus` exist. An applicability engine that treats blank as zero would
   silently classify a company as small. **Blank is `UNCHECKED`** — the same rule as null
   `verified_by`, and the lattice already expresses it.

3. **Get a personal API key.** The shared demo key returns 10 records regardless of `limit`.
   Personal-key rate limits are **not published**; measure them before this becomes a dependency.

**Still outstanding:** cross-checking values against MCA V3 for 10–20 known CINs. `mca.gov.in`
returns 403 to automated fetch, so this is a manual browser task — and it is the one check that
would confirm the *values* are right rather than merely well-formed. The portal carried a
*"sandbox environment… may be incomplete or inaccurate"* footer, so **do not treat OGD as
authoritative for a filing decision until that cross-check is done.**

**Threshold-gated provisions**, all decided deterministically and never by the model:

| Definition / gate | Provision |
|---|---|
| Small company | s.2(85) — paid-up capital and turnover |
| One Person Company | s.2(62) |
| CSR obligation | s.135 — net worth, turnover, or net profit |
| Internal audit | s.138 + Rules |
| Auditor rotation | s.139(2) + Rules |
| Board's Report — abridged form | Companies (Accounts) Rules 8(6) |

**Thresholds have been amended more than once.** Figures come from the ingested definition, never
from memory, and `source_quality` records which version is held.

## 3. Corpus — `scripts/ingest_companies_act.py`

Same shape and same rules as `ingest_posh.py`. **Hand-typing statute remains barred** — six
documented instances of a typed version silently dropping a clause.

- Source: **India Code**, the Government's own repository, **byte-verified**
- `check_transcription.py` extended to cover the new file, failing the build on a single character
  of drift
- **`source_quality` set on every provision at ingest.** The existing PoSH file has it unset on all
  30 — a known gap that must not be repeated
- The four existing MCA provisions (`secondary_reproduction`, one `DISPUTED`) are **replaced** with
  primary text, not appended to

**Phase 1 — six sections**, the annual cycle: s.96, s.92, s.137, s.134, s.173, s.2(85).
**Phase 2 — Module A**: s.12, s.88, s.117, s.149, s.152, s.153, s.161, s.164, s.2(41), s.2(62).
**Phase 3 — Module B**: s.129, s.135, s.138, s.139–147, s.73–76, s.77–87, s.179, s.180, s.185,
s.186, s.188.

## 3a. Amendment versioning — added 2026-08-16, and it is not optional

Enforcement research (`../placedon-law-research/docs/ENFORCEMENT_FINDINGS.md` §6) establishes that
**byte-verified text is not sufficient for this Act.** The operative text of the target provisions is
the product of staggered amendments with *different* commencement dates:

| Section | Current text is | Trap |
|---|---|---|
| s.92(5) | 2019 substitution **as modified by** 2020 word-substitutions | Base cut ₹50,000 → ₹10,000 |
| s.137(3) | 2019 conversion, 2020 amounts | Company max ₹10,00,000 → ₹2,00,000 |
| **s.12(8)** | **Original 2013 text, never amended** | Was never criminal, so never decriminalised |
| **s.203(5)** | **2019 text — the 2020 Act did not touch it** | *"2020 reduced everything"* is **wrong here** |
| s.134(8) | 2020 substitution | Flat, no daily accrual |

The 2019 Act commenced **retrospectively** (deemed in force 2 Nov 2018). The 2020 Act commenced in
**stages** — the penalty reductions and the s.454(3) proviso have different dates.

This is the **temporal-validity** axis that the literature search independently identified
([arXiv 2605.23497](https://arxiv.org/abs/2605.23497): *"reliable legal QA requires treating temporal
validity as a hard constraint"*). Two independent research streams reached the same requirement.

**Schema addition — every provision carries its amendment lineage:**

```python
@dataclass(frozen=True)
class Amendment:
    act: str              # "Companies (Amendment) Act, 2020"
    clause: str           # "cl.20(a)"
    effect: str           # "substitution" | "word-substitution" | "insertion"
    in_force_from: date | None    # None => commencement NOT established
    source_url: str       # the gazette PDF
```

**Rule:** a provision whose `in_force_from` is `None` for any amendment in its lineage is
**`UNCHECKED`**, not `VERIFIED` — the text may be right but we cannot assert it is operative. That
is exactly what the epistemic lattice is for, and this is the first case where the distinction is
load-bearing rather than theoretical.

### The abstention rule, revised 2026-08-16 — date, don't just find

Gazette research settled s.2(85) and, in doing so, produced a better rule than the one this
repository has used since the beginning.

**The verified chain:**

| Instrument | Paid-up | Turnover | In force |
|---|---|---|---|
| Act as enacted 2013 | ₹50 lakh | ₹2 crore | 1 Apr 2014 |
| **G.S.R. 92(E)** 1 Feb 2021 | ₹2 crore | ₹20 crore | **1 Apr 2021** — *inserted* cl.(t), deferred commencement |
| **G.S.R. 700(E)** 15 Sep 2022 | ₹4 crore | ₹40 crore | 15 Sep 2022, on publication |
| **G.S.R. 880(E)** 1 Dec 2025 | **₹10 crore** | **₹100 crore** | **1 Dec 2025 — current** |

Also operative and easily missed: the test is **conjunctive** — "or" → **"and"** by S.O. 504(E)
w.e.f. 13 Feb 2015 — and there are **four exclusions**: a public company is never a small company
*at any size* (opening words, not a proviso), nor is a holding or subsidiary company, a s.8 company,
or a company governed by a special Act. Turnover is measured *"as per profit and loss account for
the immediately preceding financial year."*

**Why this reframes the architecture.** The Act **still says "fifty lakh rupees."** A system could
cite s.2(85), link to a genuine India Code page, quote it verbatim, pass every existing check in
`verifier.py` — and be wrong by three amendments, because the operative figure lives in subordinate
legislation that has moved three times.

[Magesh et al.](https://arxiv.org/abs/2405.20362) name this **misgrounding**: an answer is
hallucinated if it *"falsely asserts that a source supports a statement."* **A citation that resolves
is not evidence of correctness.**

> ## The rule: refuse when a provision cannot be **dated**, not merely when it cannot be **found**.

Concretely, on top of §3a's `Amendment` lineage:

```python
# A provision is answerable only if we can say WHEN its text became operative.
def answerable(p: Provision, on: date) -> bool:
    if p.verified_by is None:            return False   # unchanged
    if p.as_at is None:                  return False   # NEW — undated is unanswerable
    if any(a.in_force_from is None for a in p.amendments): return False   # NEW
    return True
```

And a **prescribed-figure trap** the s.2(85) case makes concrete: where a section says *"or such
higher amount as may be prescribed"*, the operative number is **not in the Act**. The provision must
carry a pointer to the prescribing instrument, and **a section with an unresolved `prescribed_by` is
`UNCHECKED` however cleanly its own text verifies.**

This rule is strictly better than "refuse when unverified": it is **narrower** (Ask Practical Law AI
abstains 62% of the time and is the *worst* performer in the Stanford study — refusal is not
self-justifying), **more defensible**, and it explains every blocklisted source below in one
sentence — *they serve real text with no as-at date*.

### `SOURCE_BLOCKLIST` — enforced at ingest, with a `verify.py` check

The research checked secondary sources against gazette text and found four serving **wrong statute as
current**:

| Blocked for statutory text | Why |
|---|---|
| `ca2013.com` | Current and pre-amendment text **transposed** for s.172 and s.90(10)/(11) |
| `taxguru.in` | Serves **pre-2019** s.92(5)/s.137(3), with imprisonment, as current |
| **`indiankanoon.org`** | Serves **original unamended s.134(8)** with **no amendment annotation** |

**The Indian Kanoon entry is the one that matters.** It was under consideration as a judgments source
at ₹0.20/document, and it remains fine for judgments. **It must never supply statutory text** — it
serves superseded provisions without saying so, which is this product's own failure mode arriving
through the front door.

**Rule, enforced in code: statutory text comes from India Code or the Gazette. Nothing else, ever.**

## 3b. Officer liability is a separate computation

Enforcement orders show officer exposure **routinely exceeding company exposure** — GE Vernova
₹13,94,000 vs ₹5,00,000; SRA Systems ₹19,77,000 vs ₹5,00,000; Hari Machines **100% on the MD and the
Company Secretary** because the company was in liquidation.

Two structural reasons, both deterministic and both computable:

- **s.203(5)**: company side is **flat ₹5,00,000, no accrual**; each officer accrues **₹1,000/day to
  ₹5,00,000**. Long defaults invert the ratio.
- **s.12(8)**: the ₹1,00,000 cap is **per person**, so exposure scales with board size.

**And exposure multiplies by year.** Orders are issued **per financial year** — Sahil Vincom drew
four in one day, Moonlight five, Shree Nakoda **eight**. A tool reporting "you are in default"
without computing *how many years* understates by an order of magnitude.

**Requirement:** `applicability.py` returns company exposure and **per-officer exposure separately**,
across **each year of default**, with the cap logic per provision. This is arithmetic over statutory
text — the same `DerivedDate` discipline, applied to money rather than dates.

**And the s.2(60) trap is a checkable condition:** category (iii) makes **all directors** officers in
default **if the Board never designated one**. Deterministic, and exactly what the engine is for.

## 4. Verifier — `checker/verifier.py`

Two changes, both **narrowing**:

1. **`DerivedDate` admissibility**, per §0. A bare date with no derivation is still rejected.
2. **Extend `_CONSEQUENCE`.** It currently catches imprisonment, prosecution, cancellation. The
   Companies Act adds **per-day continuing penalties** and **officer-in-default** liability. A model
   asserting *"the company and every officer in default shall be liable"* where the provision says
   otherwise is the same class of error and must be caught.

## 5. What does not change

| | Why |
|---|---|
| **No confidence float** | Refused eight times, latterly with evidence: `bench_safety.py` rated two verbatim statutory quotations as more suspect than four fabrications |
| **The abstention gate** | `verified_by` null means abstain. The corporate corpus starts at **0% coverage**, exactly as intended |
| **Keyword + IDF retrieval** | Measured recall@3 **1.00** vs 0.75 for embeddings — **but see §7** |
| **The check ratchet** | Every new check carries `because=` naming the incident that bought it, and must be **mutation-tested**: break what it guards, confirm it fails, restore |
| **`distress.py`** | Stays in the codebase. Costs ₹0, calls no model, and is not contingent on commercial scope |

## 5a. Reordering, 2026-08-15 — applicability before deadlines

Market research changed the priority, and it did so with enforcement data rather than opinion.

ROC adjudication orders, FY 2024-25 — roughly **1,150 orders, ~31% of all orders ever passed**:

| Section | Subject | ~Orders | Question type |
|---|---|---|---|
| s.92 & s.137 | Annual return / financial statements | ~225 | filing |
| **s.12** | Registered office | **~175** | **applicability** |
| **s.90** | Significant beneficial owners | **~83** | **applicability** |
| s.134 | Board's report | ~55 | filing |
| s.172 | Director appointments | ~45 | applicability |
| **s.203** | Key managerial personnel | **~40** | **applicability** |

**Nobody is penalised for miscounting six months.** They are penalised for not knowing an obligation
bound them — *does the SBO regime apply to this company? must this company appoint a KMP?*

Meanwhile free ROC calendars are published by TaxGuru and ClearTax. **Due dates are commodity. What
those calendars lack is a section column** — TaxGuru's even states its dates are *"tentative."*

**Consequence for this plan.** §0's `DerivedDate` problem is real, the research in §8 confirms the
design is sound, and it remains the harder engineering. **But it is no longer first.** A calendar
competes with free; an applicability engine with a quoted section competes with nothing under the
enterprise price wall.

**s.203 and s.90 are added to Phase 1 of the corpus** — both are threshold-driven applicability
questions, both are in the top six by enforcement volume, and neither needs any date arithmetic.

## 6. Build order

**Reordered per §5a — applicability first, deadlines second.**

| | Work | Gate |
|---|---|---|
| **1** | **`CompanyFacts` + threshold applicability for s.203 (KMP), s.90 (SBO), s.2(85), s.2(62)** — tests first, fixtures, no corpus. The top enforcement categories, and no date arithmetic needed. | tests fail before they pass |
| 1b | `deadlines.py` + `DerivedDate`, **tests first**, pure arithmetic against fixtures, **no corpus** | tests fail before they pass |
| 2 | **Verifier `DerivedDate` rule + mutation test** — break the interval check, confirm failure, restore | `verify.py` GO |
| **2b** | **Scope-laundering check** — the model's narration must be verified against what the engine **executed**, not only against source text. A well-cited sentence asserting an obligation the engine did not find must fail. | mutation-tested |
| 3 | `ingest_companies_act.py`, six sections, byte-verified, `source_quality` set | `check_transcription.py` passes |
| 4 | Wire rules to the corpus — every `interval_text` resolves or raises | GO |
| 5 | `CompanyFacts` into `applicability.py`; s.2(85), s.2(62), s.135 thresholds | GO |
| 6 | `conflicts()` over the three AGM constraints | the disagreement is **reported**, not hidden |
| 7 | `bench_answers.py` extended with 20 corporate questions | three numbers: fabrication, coverage, wrong abstention |
| 8 | Six sections to a CS or lawyer for `verified_by` | **coverage 0% → measured** |

Steps 1 and 2 precede any corpus work deliberately. **If the `DerivedDate` design does not survive
its own mutation test, nothing downstream is worth building.**

## 7. The known risk, stated before it bites

`ARCHITECTURE.md` §5 records that keyword-and-scan retrieval "is correct at 30 sections and wrong
somewhere around 500." The corporate corpus targets **~50 sections**, and the Companies Act is far
more densely cross-referenced than the PoSH Act — s.134 alone references a dozen others.

`bench_retrieval.py` exists precisely so this is decided by re-running it rather than by argument.
**Re-run at step 3 and again at step 7.** If recall@3 falls below the measured 1.00, the embeddings
question reopens — with a measurement, which is the only way this repository has ever changed its
mind.

## 8. Research grounding — added 2026-08-15

A literature search was run against §0's design. Every paper below was verified by fetching its
arXiv page; leads that could not be confirmed are excluded from this section.

### The measurement that justifies the design

**[LexKairos: Benchmarking Legal Temporal Capabilities in LLMs](https://arxiv.org/abs/2608.09106)**
(Li, Feng, Huang, Ye, Xie — Aug 2026) is the only work found that isolates statutory deadline
computation as a measurable task. Its result decomposition is the important part:

| Sub-task | Frontier model accuracy |
|---|---|
| Temporal Distance Calculation — raw day arithmetic | **~98%** |
| Action Limitation Reasoning — has the period expired? | **77–83%** |

**The arithmetic is not where models fail. Selecting the right trigger event and the right statutory
interval is.** That is precisely the boundary §0 draws: the deterministic engine owns interval
selection and anchoring; the arithmetic is trivial either way. The design was reasoned from first
principles and there is now a measurement behind it.

Note the limit: LexKairos **exact-matches final dates**. It is a benchmark, not a verifier — it
would reject our derivation-based approach as unmeasurable, which is the gap §0 fills.

### The verification mechanism has precedent — in other domains

**[FinGround](https://arxiv.org/abs/2604.23588)** (Apr 2026) is the closest structural analogue.
It decomposes answers into atomic claims, then applies **type-routed verification**: computational
claims are verified by **formula reconstruction** — identify the implied formula, retrieve operands
from source, **recompute**, compare. It reports that existing detectors **miss 43% of computational
errors** requiring arithmetic re-verification.

Map directly onto `DerivedDate`: a deadline claim is routed to a date-arithmetic verifier checking
*(trigger event, interval, source provision)* and recomputing — never string-matching the result.

**[Don't Trust: Verify](https://arxiv.org/abs/2403.18120)** (Zhou et al., **ICLR 2024**) is the
canonical statement of the move: validate the **derivation** for consistency with the source
statement, not the numeric output.

**[Blawx](https://ceur-ws.org/Vol-3193/paper4GDE.pdf)** (Morris) already loads date-calculation
libraries into an s(CASP) reasoner, so date arithmetic is a first-class **symbolic** operation
rather than something a model performs. Engineering precedent for "the engine computes the date."

**Conclusion on novelty:** the mechanism is a **well-grounded transfer**, established independently
in mathematics, finance and chemistry. The **legal-temporal instantiation appears novel** — no work
was found formalising a deadline as a verifiable triple where the interval and trigger are checked
against source text and only the computation is exempt from verbatim matching.

### Why the graph-constrained approaches cannot do this

**[Graph-constrained Reasoning](https://arxiv.org/abs/2410.13080)** (ICML 2025) achieves zero
reasoning hallucination by constraining the decoder to valid graph paths. **[Falkor-IRAC](https://arxiv.org/abs/2605.14665)**
applies reject-unless-traceable to Indian judgments.

Both would **reject every correct computed deadline**, because a trie or graph can only admit values
that already exist as nodes. This is the exact failure §0 identifies, now confirmed as a property of
the method rather than a suspicion. Falkor-IRAC was checked specifically: it says nothing about
deadlines, dates or computed values.

### Two cautions that cut against instinct

**Do not cite at sub-sentence granularity.**
[Wang et al.](https://arxiv.org/abs/2604.01432) (Apr 2026) measure that fine-grained citation
**degrades attribution by 16–276%**; paragraph-level is optimal. This **contradicts and withdraws**
part of the reasoning in `PROVIDER_DECISION.md` §5, corrected there. Cite at provision level; meet
the precision requirement in the engine.

**Guard against scope laundering.**
[Know Your Limits](https://arxiv.org/abs/2606.16118) (Jun 2026) names the failure where a model
**reports a conclusion inconsistent with what the solver actually executed** — well-cited, plausible,
and not what the engine decided. Since our model narrates `applicability.py`'s output, this is a
live risk and needs its own check: **the narration must be verified against the execution, not
merely against the source text.** Added to the build order as step 2b.

### Supporting

- **[Catala](https://arxiv.org/abs/2103.03198)** (ICFP 2021) — statutes as executable code on
  default logic; found a bug in an official government implementation. Design precedent for the
  deterministic engine.
- **[Reasoners or Translators?](https://arxiv.org/abs/2605.16052)** (May 2026) — neuro-symbolic
  pipelines do not beat LLM baselines on *correct* decisions but substantially **reduce errors by
  abstaining when generated code fails verification**. That is this product's value proposition,
  measured by someone else.
- **[AbstentionBench](https://arxiv.org/abs/2506.09038)** (Jun 2025) — abstention is unsolved and
  **scaling does not help**. Justifies abstention as a hard architectural gate rather than a
  prompted behaviour.
- **[Hallucination-Free?](https://arxiv.org/abs/2405.20362)** (Magesh et al., *JELS* 2025) —
  the 17–33% figure, peer-reviewed, still the reference study.
- **[Asking For An Old Friend](https://arxiv.org/abs/2605.23497)** (May 2026) — temporal *validity*
  (which version of the law applies) is a second temporal axis we will need, since Indian statutes
  amend constantly. Web search **worsens** this through recency bias.

### The significant negative result

**No Indian statutory-reasoning corpus exists.** Every Indian legal NLP resource located — IL-TUR,
ILDC, InLegalBERT, NyayaAnumana — is built on **judgments**. No obligation- or deadline-annotated
dataset over the Companies Act, Income-tax Act, GST or labour codes. No academic work on Indian
statutory compliance rule engines.

An evaluation set of Indian statutory deadlines would, as far as this search can establish, be the
first. `bench_answers.py` at step 7 is that set.

## 9. What this does not build

**No drafting. No advice on structure. No document review. No filing submission to the MCA.**

Interviews with practising lawyers established that methodology varies enormously and that drafting
is precisely where professional trust ends — *"robotic and irrelevant"*, and *"75% should be drafted
by the person."*

This plan builds the **substrate**: dates, thresholds, applicability, citations. The judgment stays
with the professional, which is what that 75/25 split asked for.
