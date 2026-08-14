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

## 6. Build order

| | Work | Gate |
|---|---|---|
| 1 | `deadlines.py` + `DerivedDate`, **tests first**, pure arithmetic against fixtures, **no corpus** | tests fail before they pass |
| 2 | **Verifier `DerivedDate` rule + mutation test** — break the interval check, confirm failure, restore | `verify.py` GO |
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

## 8. What this does not build

**No drafting. No advice on structure. No document review. No filing submission to the MCA.**

Interviews with practising lawyers established that methodology varies enormously and that drafting
is precisely where professional trust ends — *"robotic and irrelevant"*, and *"75% should be drafted
by the person."*

This plan builds the **substrate**: dates, thresholds, applicability, citations. The judgment stays
with the professional, which is what that 75/25 split asked for.
