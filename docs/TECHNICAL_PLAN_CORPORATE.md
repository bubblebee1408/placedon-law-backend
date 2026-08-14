# Technical plan — Companies Act 2013 compliance calendar

Written 2026-08-15. Companion to `../placedon-law-research/docs/BUSINESS_PLAN_CORPORATE.md`.

Everything in `ARCHITECTURE.md` stands: the model never decides applicability, the verifier rejects
unsourced claims, status is ordinal and there is no confidence float. This document covers what
changes, and **one thing that genuinely breaks** and must be solved before a single date is shipped.

---

## 0. The problem that has to be solved first

**A due date is a number that does not appear in the statute.**

s.96 says an AGM must be held *"within six months from the date of closing of the financial year."*
For a company with FY ending 31 March 2026, the answer a user needs is **30 September 2026**.

Search the Act for "30 September 2026" and it is not there. It cannot be — the Act is not written
per company.

Now read `verifier.py`'s rule: **reject any answer containing a figure absent from the source text.**

> **As it stands, the verifier would reject every correct deadline this product computes, as a
> fabrication.** And if we relax the rule to let dates through, we delete the mechanism that makes
> the whole product trustworthy.

This is not a bug to patch later. It is the central design question of the corporate scope, and
getting it wrong in either direction destroys something: relax the verifier and fabricated dates
ship; keep it and nothing ships.

### The resolution: verify the interval, not the result

A deadline is not an atomic claim. It is an **arithmetic** with three inputs, each of which *is*
checkable:

```
  anchor    31 March 2026        <- a fact the USER supplied (their financial year end)
  interval  "six months"         <- MUST appear verbatim in the cited provision
  operation from the close of    <- the provision's own words, quoted
  ─────────────────────────────
  result    30 September 2026    <- derived, never retrieved, never generated
```

So a new claim type is introduced, and it carries its own derivation:

```python
@dataclass(frozen=True)
class DerivedDate:
    result: date                  # 2026-09-30
    anchor: date                  # 2026-03-31, from the user
    anchor_label: str             # "close of the financial year"
    interval_text: str            # "six months" — verbatim from the provision
    interval: relativedelta        # parsed, and re-derivable from interval_text
    citation: str                 # "s.96(1), Companies Act 2013"
    quote: str                    # the provision's own sentence, verbatim
```

**The verifier's new rule:** a `DerivedDate` is admissible **iff** `interval_text` appears verbatim
in the cited provision **and** re-running the arithmetic on `(anchor, interval)` reproduces
`result` exactly. The date itself is never looked for in the source, because it is not a claim about
the source — it is a claim about arithmetic *on* the source.

**What the user sees is the derivation, not just the answer:**

> **30 September 2026.**
> Derived: your financial year closed **31 March 2026**; s.96(1) requires the meeting
> *"within six months from the date of closing of the financial year"*. **Six months** from
> 31 March 2026.

That is checkable by hand in five seconds, which is the standard the rest of this repository holds.

**This preserves the ratchet rather than weakening it.** A model that emits a bare date still fails.
Only a date arriving with a verified interval and reproducible arithmetic passes.

---

## 1. New module — `checker/deadlines.py`

Pure functions, no model, no I/O beyond the corpus. Mirrors `distress.py` in shape: deterministic,
self-testing, run directly.

```python
def compute(rule: DeadlineRule, facts: CompanyFacts) -> DerivedDate | Abstention
def applicable(rule: DeadlineRule, facts: CompanyFacts) -> bool
def calendar(facts: CompanyFacts, on: date) -> list[DerivedDate]   # everything due, ordered
```

**Rules are data, extracted from provisions — never hand-typed:**

| Rule | Provision | Anchor | Interval |
|---|---|---|---|
| AGM | s.96(1) | close of financial year | six months |
| AGM gap | s.96(1) proviso | previous AGM | fifteen months |
| First AGM | s.96(1) proviso | incorporation | nine months |
| Annual return | s.92(4) | date of AGM | sixty days |
| Financial statements | s.137(1) | date of AGM | thirty days |
| Board meetings | s.173(1) | previous meeting | one hundred and twenty days |

**Every interval string above must be present verbatim in the ingested provision or the rule is
refused at load time.** A rule whose `interval_text` is not found raises, exactly as
`register.py` raises on a `DATE_NOTIFIED` with no `reply_verbatim`.

### The traps, named now because they will otherwise ship

- **First AGM is a different rule.** Nine months from incorporation, not six from FY close. A
  calendar that applies the general rule to a company in its first year is wrong in the direction
  that costs a penalty.
- **Three constraints on the AGM at once** — six months from FY close, fifteen months from the last
  AGM, and (first year) nine months from incorporation. The binding date is the **earliest**, and
  `conflicts()` must report when they disagree rather than silently taking the minimum. This is the
  same weakest-link-hides-the-disagreement problem `ARCHITECTURE.md` §3 describes for s.9.
- **s.92 and s.137 anchor to the AGM's *actual* date, not its due date.** If the AGM is held early,
  the filing deadlines move earlier. Anchoring to the deadline is a silent off-by-weeks error.
- **Extensions exist.** The Registrar may extend the AGM by up to three months on application. The
  product must not present the base date as immovable — it reports the statutory date and quotes
  the extension provision.
- **"Financial year" is defined** — s.2(41), ordinarily ending 31 March. Do not assume; read it.

## 2. Applicability — extending `applicability.py`

Corporate obligations turn on **thresholds**, which is what `applicability.py` already does for
PoSH's ten-employee test. The new inputs:

```python
@dataclass(frozen=True)
class CompanyFacts:
    incorporated_on: date
    financial_year_end: date        # s.2(41)
    paid_up_capital: int            # rupees
    turnover: int                   # rupees
    is_public: bool
    is_one_person_company: bool     # s.2(62)
    borrowings: int
    last_agm: date | None
    last_board_meeting: date | None
```

**Small company — s.2(85)** and **OPC — s.2(62)** are the definitions that gate a large share of the
Act, and both are threshold tests on capital and turnover. They are decided **deterministically**,
never by the model. The thresholds have been amended more than once, so the figures come from the
ingested definition and `source_quality` records which version.

**The existing OPC/small-company abstention is retained.** `board_report.py` already abstains on
Rule 8(6) because whether Rule 8A requires an IC statement anyway is disputed and is Question 6 in
the lawyer pack. That abstention is correct and must survive the migration.

## 3. Corpus — `scripts/ingest_companies_act.py`

Same shape and same rules as `ingest_posh.py`. **Hand-typing statute remains barred** — six
documented instances of a typed version silently dropping a clause, including s.4(2)(c) losing the
one-half-women proviso.

- Source: **India Code**, the Government's own repository, byte-verified
- `check_transcription.py` extended to cover the new file
- **Phase 1, six sections** — s.96, s.92, s.137, s.134, s.173, s.2(85) — the annual cycle
- Phase 2, the remaining ~44: s.139, s.12, s.88, s.77, s.73, s.188, s.153, s.164, s.2(41), s.2(62)
- **`source_quality` is set on every provision at ingest.** The existing PoSH file has it unset on
  all 30, which is a known gap; the new file must not repeat it.

The four existing MCA provisions carry `secondary_reproduction`, `secondary_reproduction_paraphrase`
and one **`DISPUTED`**. These are replaced with Gazette or India Code text, not appended to.

## 4. Verifier — `checker/verifier.py`

Two changes, both narrowing:

1. **`DerivedDate` admissibility**, per §0 — interval verbatim in source, arithmetic reproducible.
   A bare date with no derivation is still rejected.
2. **Extend `_CONSEQUENCE`.** It currently catches imprisonment, prosecution, cancellation. The
   Companies Act adds **per-day continuing penalties** and **officer-in-default** liability — a
   model asserting "the company and every officer in default shall be liable" when the provision
   says otherwise is the same class of error and must be caught.

## 5. What does not change, and must not

| | Why |
|---|---|
| **No confidence float** | Refused eight times, latterly with evidence (`bench_safety.py`) |
| **The distress route** | Free, model-free, unconditional. Not contingent on business scope. |
| **The abstention gate** | `verified_by` null still means abstain. The corporate corpus starts at 0% coverage exactly as PoSH did. |
| **Keyword + IDF retrieval** | Measured recall@3 1.00 vs 0.75. **But see §7 — this is the design decision most likely to break at ~50 sections.** |
| **The 50-check ratchet** | Every new check carries `because=` and must be mutation-tested |

## 6. Build order

| | Work | Gate |
|---|---|---|
| 1 | `deadlines.py` with `DerivedDate`, tests first, **no corpus** — pure arithmetic against fixtures | tests fail before they pass |
| 2 | **Verifier `DerivedDate` rule + mutation test** — break the interval check, confirm it fails | `verify.py` GO |
| 3 | `ingest_companies_act.py`, six sections, byte-verified, `source_quality` set | `check_transcription.py` passes |
| 4 | Wire `deadlines.py` to the corpus; every rule's `interval_text` must resolve or raise | GO |
| 5 | `CompanyFacts` into `applicability.py`; s.2(85) and s.2(62) thresholds | GO |
| 6 | `conflicts()` over the three AGM constraints | the disagreement is reported, not hidden |
| 7 | `bench_answers.py` extended with 20 corporate questions | three numbers, as always |
| 8 | Six sections to a CS or lawyer for `verified_by` | **coverage 0% → measured** |

Steps 1 and 2 come **before** any corpus work, deliberately: if the `DerivedDate` design does not
survive its own mutation test, nothing downstream is worth building.

## 7. The known risk, stated before it bites

`ARCHITECTURE.md` §5 says the keyword-and-scan retrieval "is correct at 30 sections and wrong
somewhere around 500." The corporate corpus targets ~50, plus 30 PoSH and 14 Rules — **roughly 100
provisions**, and the Companies Act has far more internal cross-referencing than PoSH.

`bench_retrieval.py` exists precisely so this is decided by re-running it rather than by argument.
**Re-run it at step 3 and again at step 7.** If recall@3 falls below the measured 1.00, the
embeddings question reopens — and it reopens with a measurement, which is the only way this
repository has ever changed its mind.

## 8. What this does not build

No drafting. No advice on structure. No document review. No filing submission to MCA.

Three interviews established that **strategy does not standardise and drafting is where trust
ends**. This plan builds the substrate — dates, thresholds, applicability, citations — and leaves
the judgment to the professional, which is what the 75/25 split asked for.
