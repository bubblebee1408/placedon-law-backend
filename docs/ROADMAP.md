# Roadmap — 8 weeks to a lawyer-reviewable prototype

One workflow. One document family. Twelve sections. Measured before claimed.

## The workflow being built

> Review a corporate document dated D and identify **potentially applicable** requirements under
> the MVP sections, with primary-source citations, effective dates, and explicit uncertainty.

Never "this document is compliant". That is a legal conclusion and we do not make it.

## Reality check performed 20 Aug 2026, before planning

| Finding | Consequence |
|---|---|
| Corpus has **527 sections but no section numbers** — content begins at "(1)", the sub-section | **Blocker.** s.173 is not findable. W1 fixes this first. |
| India Code `/handle/` and `SectionPageContent` returned **404 on 3 consecutive attempts** (worked at 09:50 the same day) | Re-fetch is impossible today. Corpus on disk is safe and hashed. |
| The full-Act **PDF still serves** (3.28 MB) and carries the arrangement-of-sections | The section-number index is derivable from the PDF, offline. |

**Design consequence: never depend on a live fetch at request time.** The corpus is a local, hashed
artifact. Ingestion is a batch job that tolerates the source being down.

---

## Week 1 — Section index and scope freeze

**The single blocking task.** Without a `section_number -> section_id` map nothing downstream works.

| Step | Detail | Done when |
|---|---|---|
| 1.1 | Extract the arrangement-of-sections from the local PDF text | All section numbers + titles listed |
| 1.2 | Match each to a corpus record by first-200-character text alignment | ≥95% of 527 mapped, unmatched listed explicitly |
| 1.3 | Hand-verify the 12 MVP sections + the 5 extensions | 17/17 confirmed by reading the text |
| 1.4 | Write `corpus/companies_act/_index.json` | number, title, section_id, confidence, method |
| 1.5 | Freeze scope: 4 document classes, 12 sections, 5 applicability states | `docs/MVP_SECTIONS.md` committed |

**Gate:** `section_by_number("173")` returns the right text, hand-checked. **If <95% map, stop and
re-plan** — the whole roadmap rests on this.

## Week 2 — Corpus audit and provenance

| Step | Detail |
|---|---|
| 2.1 | Every record carries source_id, url, retrieval_date, sha256, current-or-historical flag |
| 2.2 | Separate **current consolidated** from **historical** text in storage, not just in comments |
| 2.3 | Ingest the subordinate Rules the 12 sections depend on — Meetings of Board and its Powers Rules; Management and Administration Rules |
| 2.4 | `scripts/validate_corpus.py` — fails on missing url, missing type, invalid dates, duplicate ids/hashes, mixed current+historical |
| 2.5 | Retire HR-era debris: PoSH corpus, `hr-ops-researcher`, `trust-boundary-reviewer` (R-010) |

**Gate:** every finding can point to a traceable source and a date. Retracted evidence excluded from
active conclusions but preserved for audit.

## Week 3 — Document taxonomy

Four classes only: `BOARD_NOTICE` · `BOARD_RESOLUTION` · `AGM_NOTICE` · `SHAREHOLDER_RESOLUTION`
plus `UNKNOWN` and `AMBIGUOUS`.

Per class define: required facts · optional facts · common variants · candidate provisions ·
**exclusion rules** · uncertainty triggers · expected output.

Known extraction traps already observed in the real corpus, which the classifier must survive:
- Regulation 30 outcome filings also use notice language
- Modern notices are VC/OAVM, so proxy provisions may not apply
- Some PDFs extract letter-spaced (`i s  h e r e b y`), defeating word-boundary patterns
- Ligature glyphs (`beneﬁt`, U+FB01)

**Gate:** the system stops applying every rule to every document. `UNKNOWN` is a correct answer.

## Week 4 — Benchmark, labels frozen before evaluation

30-50 documents: 10 compliant · **10 with known defects** · 5 board notices · 5 resolutions ·
5 AGM documents · 5 amendment/date cases · 5 ambiguous cases that *should* abstain.

Each carries an **independently produced** label: document_type, facts, relevant_date,
expected_rules, expected_findings, expected_citations, expected_abstentions, reviewer, review_date.

**Non-circularity is the whole point.** The label author must not be the rule author, and the
expected source must not be the parser input. The first attempt at a benchmark in this project
failed exactly here — see `docs/RETRACTIONS.md` R-1.

**Gate:** labels frozen and committed **before** the system is run against them.

## Week 5 — Retrieval and citations

Search the validated corpus with metadata and date filters. Every finding emits:

```
Finding · Legal basis · Source · Provision · Applicable period · Reason · Confidence ·
Human review required
```

**Gate:** no material legal finding appears without source provenance. A finding whose source cannot
be resolved is blocked, not downgraded.

## Week 6 — Classification and applicability engine

Rule schema, not regex sprawl:
`rule_id · title · document_types · required_facts · trigger_conditions · exclusion_conditions ·
effective_from · effective_until · source_ids · confidence · review_required`

States: `APPLICABLE` · `POSSIBLY_APPLICABLE` · `NOT_APPLICABLE` · `INSUFFICIENT_FACTS` ·
`SOURCE_UNCERTAIN`

**Gate:** the engine can output INSUFFICIENT_FACTS. A binary pass/fail engine fails this gate.

## Week 7 — Evaluate against the frozen benchmark

Measure: classification accuracy · citation accuracy · applicability precision · **recall** ·
false positives · **false negatives** · effective-date accuracy · abstention quality.

**Do not tune rules against individual benchmark documents.** That reintroduces circularity.

**Gate:** no performance claim published without sample size, test design and limitations.

## Week 8 — Lawyer-facing prototype

Upload/paste → ask for missing facts → render findings with citations, confidence and uncertainty →
exportable report → feedback capture.

**Gate:** a lawyer can review the output without reading source code.

---

## Go / no-go gates

| Gate | Proceed only if |
|---|---|
| 1 Scope | One user, one workflow, limited document types, non-goals documented |
| 2 Corpus | Sources traceable, retracted data excluded, current and historical separated |
| 3 Benchmark | Labels independent, defective **and** ambiguous cases present, false negatives measurable |
| 4 Prototype | Citations with findings, uncertainty visible, unsupported conclusions blocked, can request missing facts |
| 5 External test | Testers understand limitations, no client-confidential data required, feedback traceable to document and source |

## Standing risks

| Risk | Mitigation |
|---|---|
| **India Code instability** — dynamic endpoints 404 as of 20 Aug | Corpus is local and hashed; ingestion is batch, never at request time; PDF is the fallback |
| Reconstruction still unbenchmarked (R-1) | W4 builds a non-circular benchmark before any accuracy claim |
| False negatives never measured | W4 mandates 10 known-defective documents |
| Scanner over-fires | Frozen until taxonomy lands (W3), then rebuilt rule-by-rule |
| Zero lawyer contact | Gates **claims**, not development. Expert review before any professional-use statement |
| Market model is CS-based | R-011: rebuild for the lawyer segment before any external figure |
