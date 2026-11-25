# R-004: Non-Circular Reconstruction Benchmark Design

## Problem
Prior benchmark (retracted R-1) compared our reconstruction against India Code's own current consolidation — circular. Need an independent source.

## Available Independent Sources

| Source | What it has | Access | Independence |
|--------|------------|--------|-------------|
| **WIPO Lex** (wipo.int/wipolex) | As-enacted 2013 text (Act 18/2013) + consolidated-to-2021 text | Public PDF, no auth | YES — different publisher, different digitisation pipeline |
| **PRS India** | As-enacted 2013 text (Gazette reproduction) | Public PDF | YES — legislative research org, independent scan |
| **Indian Kanoon** (amending Acts) | 24 amended spans already corroborated | Public, robots-compliant | YES — already used in CORROBORATION.md |
| **eGazette.gov.in** | Official Gazette PDFs (original + amendment notifications) | Public, may be patchy | YES — primary authority |
| Manupatra / SCC Online | Consolidated Acts with amendment annotations | Paywalled, no API | YES but inaccessible without subscription |

## Benchmark Design

### Tier 1: As-Enacted Baseline (section-level)
**Source:** WIPO Lex original 2013 PDF + PRS India PDF
**Method:**
1. OCR/extract both PDFs to per-section text
2. Compare each section against our corpus `corpus/companies_act/*.json` as-of 2013-08-29 (the as-enacted date, before any amendment)
3. Normalize whitespace, punctuation, numbering artifacts
4. Score: exact match, near-match (>0.95 similarity), mismatch

**Sample:** All 470 sections as originally enacted (excluding later insertions like 3A, 10A)
**PASS:** ≥95% exact or near-match after normalization
**FAIL:** Any section with semantic divergence (not just whitespace/formatting)

### Tier 2: Amendment Span Corroboration (expand existing)
**Source:** Indian Kanoon amending Acts (already 24/40, expand to remaining)
**Method:** Already built in `checker/corroborate.py`. Extend to cover Companies (Amendment) Act 2019 via eGazette (Indian Kanoon gap).
**PASS:** 0 conflicts; NO_WITNESS count ≤ 5

### Tier 3: Point-in-Time Spot Check
**Source:** WIPO Lex consolidated-to-2021 text
**Method:**
1. Reconstruct our corpus as-of 2021-08-13 (date of Act 33/2021)
2. Compare 20 randomly selected sections against WIPO's consolidated version
3. Score section-level match

**Sample:** 20 sections, stratified: 10 amended at least once, 10 never amended
**PASS:** ≥18/20 exact or near-match
**FAIL:** Any section with wrong amendment applied or missing

## What This Does NOT Cover
- Sections amended after 2021 (WIPO text stops at Act 33/2021)
- Commencement-date accuracy (which sections were in force when)
- Schedule/table formatting fidelity

## Implementation Order
1. **Tier 1 first** — cheapest, highest signal, unblocks "is our as-enacted baseline correct?"
2. **Tier 2 expansion** — incremental on existing `corroborate.py`
3. **Tier 3 last** — requires reconstruction engine to work correctly at Tier 1 first

## Key Constraint
Never repair a defective source. If WIPO/PRS disagrees with our text, flag it — do not auto-correct either side. The benchmark measures; it does not fix.
