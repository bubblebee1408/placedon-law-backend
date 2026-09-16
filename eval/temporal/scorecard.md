# Temporal retrieval scorecard

**Generated:** 2026-09-14 · `eval/temporal/harness.py` · regenerate with
`PYTHONPATH=. python3 eval/temporal/harness.py`

Measures whether consulting effective-date metadata changes what gets retrieved,
on this repository's own law. FiscalQA (arXiv 2608.09393) reports naive RAG over a
current-version corpus almost never retrieves the date-applicable provision. This
reproduces that on Indian corporate law and puts a number on our side of it.

## The three numbers

| | A — naive current corpus | B — date-conditioned |
|---|---|---|
| Overall (25 scored) | **56%** | **100%** |
| On the 14 answerable | **43%** | **100%** |
| **On the 8 historical** | **0%** | **100%** |
| Confident wrong answers | **11** | **0** |
| Wrong refusals | 0 | 0 |
| Correct refusals | 8 / 11 | 11 / 11 |

**The third row is the claim.** The first two understate the gap, because naive
retrieval is right by coincidence whenever the question happens to be about today.
Restricting to dates outside the current window removes the coincidence, and the
naive condition scores **zero** — not "worse", but never once right.

The row that matters commercially is the fourth. The naive condition does not fail
by declining to answer. It answers 11 times with a real,
citable, currently-in-force figure that did not govern on the date asked. That is
the failure mode a practitioner cannot detect by looking at the output.

## What the two conditions are

    A  NAIVE_CURRENT      ignores the query date, returns the version in force
                          today. Not a strawman: this is what a consolidated Act,
                          a commercial database's "current text", and a vector
                          index over today's corpus all do.
    B  DATE_CONDITIONED   selects the version whose [effective_from, effective_to]
                          contains the query date; refuses when none does.

The only difference is whether effective-date metadata is consulted. Same corpus,
same questions, same scorer.

## Scoring

Deterministic. Numeric nuggets compare value against gold with a tolerance of
under half a rupee — a threshold is exact, and "approximately four crore" is not a
legal position. Selection nuggets are a regex on the instrument name.

**There is no LLM judge, and that is a methodological requirement rather than a
cost saving.** A model asked to grade these brings the same recency prior that
condition A is being measured for; shown a 2024 question answered with the 2025
figure, it tends to accept the newer number as correct-and-updated. A judge that
shares the bias cannot measure it. The harness asserts this structurally by
parsing its own imports.

It also does not import `checker/`. The benchmark measures a retrieval *strategy*,
not this repository's implementation of one, so a bug in the engine cannot flatter
its own score.

## Refusals are scored, not excused

11 of 25 questions have no servable answer:

- **dates before any held version** — nothing was acquired covering 2019 or 2021,
  and the correct output is a refusal, not the oldest version we happen to hold;
- **the criminal codes** — `code_transition` holds commencement dates and anchors,
  but the code text is not in the corpus, so every verdict is
  `INSTRUMENT_NOT_HELD`;
- **the allotment window** — registered, hashed, and **not attested**. Rule 12(1)
  has been stable at thirty days since 2014, so a naive lookup would be right for
  every date. It is still refused, because storage is not review.

That last one is the negative control, and it is not the kind the brief expected. A
benchmark built only from thresholds that moved would flatter date-conditioning. A
stable provision that we nonetheless refuse to serve tests the opposite property.

## Provenance — read this before quoting any number above

Every artifact behind this corpus is an **India Code rendering, not a signed
e-Gazette PDF**. Measured with `scripts/verify_document.py`:

| Artifact | Signature | |
|---|---|---|
| `pas_rules_2014.pdf` | `NOT_PRESENT` | India Code serves an unsigned rendering |
| `gsr642e_2020.pdf` | `INVALID` | genuine CCA India chain, but content appended after signing |

India Code is an official government portal and a permitted source, so the
artifacts are usable. **They are not cryptographically established as the Gazette
and nothing here may imply they are.**

## What this does not establish

- Not accuracy on free-text questions. Every question is a date-plus-threshold or
  date-plus-code-selection lookup with a deterministic answer.
- Not end-to-end product accuracy. It measures retrieval strategy, not extraction,
  not narration, not the Word add-in.
- Not demand. It is an engineering measurement.
- 3 questions are excluded as `PENDING_HUMAN` — listed below,
  awaiting a lawyer. None was guessed.

## PENDING_HUMAN — a lawyer must gold-label these

- **T26** (2025-12-01) — A company incorporated 10-11-2025 with Rs 6 crore paid-up capital prepares accounts for FY2025-26. Which threshold applies to its small-company status for that year?
  - *why it is not auto-labelled:* turns on whether the test is applied at a balance-sheet date or across the year; needs a lawyer, not a date lookup
- **T27** (2024-07-01) — A continuing offence began 01-03-2024 and ran to 01-09-2024. Which code governs?
  - *why it is not auto-labelled:* code_transition escalates this as STRADDLES; the answer is contested and not a date comparison
- **T28** (2021-02-01) — Did G.S.R. 37(E) alter the return-of-allotment period, given it omitted sub-rule (6) of rule 12?
  - *why it is not auto-labelled:* requires reading the omitted sub-rule and its interaction with sub-rule (1)

## The question set

| id | date | instrument | gold |
|---|---|---|---|
| T01 | 2024-06-14 | `small_company.paid_up_capital` | 40000000 |
| T02 | 2023-01-09 | `small_company.paid_up_capital` | 40000000 |
| T03 | 2025-11-30 | `small_company.paid_up_capital` | 40000000 |
| T04 | 2025-12-01 | `small_company.paid_up_capital` | 100000000 |
| T05 | 2026-09-13 | `small_company.paid_up_capital` | 100000000 |
| T06 | 2022-09-15 | `small_company.paid_up_capital` | 40000000 |
| T07 | 2022-09-14 | `small_company.paid_up_capital` | REFUSE |
| T08 | 2019-04-01 | `small_company.paid_up_capital` | REFUSE |
| T09 | 2024-06-14 | `small_company.turnover` | 400000000 |
| T10 | 2025-11-30 | `small_company.turnover` | 400000000 |
| T11 | 2025-12-01 | `small_company.turnover` | 1000000000 |
| T12 | 2026-09-13 | `small_company.turnover` | 1000000000 |
| T13 | 2021-06-30 | `small_company.turnover` | REFUSE |
| T14 | 2023-05-12 | `criminal.substantive_code` | REFUSE |
| T15 | 2024-06-30 | `criminal.substantive_code` | REFUSE |
| T16 | 2024-07-01 | `criminal.substantive_code` | REFUSE |
| T17 | 2025-02-01 | `criminal.procedural_code` | REFUSE |
| T18 | 2023-03-15 | `criminal.procedural_code` | REFUSE |
| T19 | 2024-06-14 | `allotment.return_window_days` | REFUSE |
| T20 | 2016-08-01 | `allotment.return_window_days` | REFUSE |
| T21 | 2026-09-13 | `allotment.return_window_days` | REFUSE |
| T22 | 2025-12-02 | `small_company.paid_up_capital` | 100000000 |
| T23 | 2022-09-15 | `small_company.turnover` | 400000000 |
| T24 | 2025-06-30 | `small_company.paid_up_capital` | 40000000 |
| T25 | 2026-01-15 | `small_company.turnover` | 1000000000 |


---

# Condition C — a real external corpus

Added 14-09-2026. Condition A is a model of naive retrieval that I wrote, and a
strawman I built cannot be evidence about anyone else's system. Condition C is
naive retrieval somebody else built, at scale, well.

**[Open India Law](https://github.com/Vaquill-AI/open-india-law)** — 1.1M
legislation provisions, 12.8M judgments, CC BY 4.0, Apache-2.0 code, actively
maintained. Their own data-quality audit opens by admitting that `jurisdiction`
and `category` are byte-identical and neither is a jurisdiction. That is the same
discipline this repository tries to hold, and it is why their corpus is the right
one to measure against rather than a competitor to dismiss.

`in_central_legislation.parquet` v2026.08.1, 74,484 central provisions, read
directly. No scraper of theirs was run — CLAUDE.md forbids running crawlers we
have not read.

## The result

| | on the 10 paid-up questions it reaches | historical subset |
|---|---|---|
| **C — Open India Law** | 3 correct / **7 wrong** | **0 of 5** |

## Why it cannot be otherwise

Their schema carries **no `effective_from` and no `effective_to`** — verified by
search across the whole repository, both return zero occurrences. What it has:

- `in_force` — a **boolean**
- `amendment_count` — an **integer**, and `0` on 1,214 of the 1,235 Companies Act rows

The schema records *that* amendments exist without recording *when* any of them
took effect. A date cannot be applied, so the same text is served whatever date
is asked. This is not a defect in their engineering; it is the shape of every
current-text corpus, which is the point being measured.

## The trap, verbatim from their data

Their s.2(85) — stored, incidentally, under `section_number: "3"`, so a
section-number filter misses it — reads:

> "small company" means a company, other than a public company,— (i) paid-up
> share capital of which does not exceed **fifty lakh rupees** or such higher
> amount as may be prescribed which shall not be more than[1] **[ten crore rupees]**

Three numbers, all real, all in the Act:

| reading | what it actually is | correct for |
|---|---|---|
| **fifty lakh** | the as-enacted 2013 base figure | no date since 2021 |
| **ten crore** | the statutory **CEILING on what may be prescribed** | — |
| ₹4 crore / ₹10 crore | the **prescribed** figure, in a delegated Rule | the dates actually asked |

**The operative number is not in this text.** It is in G.S.R. 700(E) and G.S.R.
880(E), and their corpus has no row for either — it holds Acts, and the threshold
lives in Rules.

And the trap closes: "ten crore" **coincides with today's prescribed figure**,
because G.S.R. 880(E) happened to prescribe the maximum the Act permits. So a
retrieval system reading that text answers ₹10 crore, looks correct today, and is
**right for the wrong reason** — it has read a ceiling as a prescription. Ask it
about June 2024 and the same reasoning returns the same number, now wrong.

That is the failure mode in its most dangerous form: not a hallucination, not a
missing citation, but a real provision correctly quoted and wrongly applied.

## Two further measurements, for completeness

**Every `source_url` in their central file — all 74,484 — points at
`www.indiacode.nic.in`, which returns 404.** India Code moved domain; this
repository recorded that weeks ago. To their credit every row also carries a
`mirror_url` on their own host, and it resolves and serves the PDF.

That mirror was then run through `scripts/verify_document.py`:

| | signature |
|---|---|
| their mirrored Companies Act PDF | `NOT_PRESENT` |

Consistent with this repository's own provenance census — **1 of 13 held
artifacts carries a valid signature**, and the only intact one came from the
issuing ministry rather than an aggregator. Their mirror is a copy of an India
Code rendering, which is one further hop from the signed Gazette.

## What condition C does NOT establish

- Not that Open India Law is bad. It is a serious, well-audited, generously
  licensed corpus and it is better than anything this repository holds on
  breadth, by three orders of magnitude.
- Not that we could not use it. For scope breadth — showing the *text* of the
  eight bodies `scope.py` currently refuses on — it would be a real gain.
- Not a competitive claim. It is a measurement of one property, on one provision,
  and that property is the only one this project has ever claimed.

**What it does establish:** a well-resourced team published 1.1M provisions of
Indian legislation with no temporal versioning. If point-in-time were easy, or
commodity, it would be in that file. It is not.
