# CLAUDE.md

## Product
Placedon — an India-first legal intelligence and audit platform.

## Current focus
An **evidence-backed audit layer for Indian corporate documents**, starting with the Companies Act
2013 and related compliance workflows. Not a general legal chatbot. Not a foundation-model project.

## The wedge
Given a corporate document, determine whether it is:
1. the correct document type,
2. applicable to the relevant company and date,
3. legally current,
4. supported by primary or clearly-labelled secondary evidence,
5. missing required information,
6. safely classifiable as VERIFIED / PARTIALLY_VERIFIED / UNVERIFIED / INAPPLICABLE /
   POTENTIAL_ISSUE / STALENESS_WARNING.

## Why an audit layer and not a generator
Document *generation* is commoditised: ComplyRelax is free to ICSI members until 31 Mar 2029.
But its own instruction PDFs state that customising a template stops legal updates and editing a
variable stops company-data linking — so every real firm's documents are a private fork drifting
from both the law and its data, unreachable by any vendor update including a competitor's. The
defect is only detectable at the output. That is where an audit layer sits.

## Non-negotiable rules
- Never claim legal accuracy without an independent benchmark.
- **Never use a current consolidated Act as pre-amendment ground truth.** This exact mistake was
  made and retracted — see `docs/RETRACTIONS.md`.
- Never call a finding a defect when the rule is inapplicable to the document type. Minutes checks
  must not fire on notices.
- Every legal finding carries source, date, rule ID, reasoning, and confidence.
- Unknown document type produces classification uncertainty, not substantive defects.
- Preserve uncertainty. Never silently drop an unresolved marker.
- Never repair a defective government source. Flag it, preserve it verbatim.
- Do not bypass the MCA WAF, robots restrictions, access controls, or source terms.
- Do not obtain private minutes or confidential company documents.
- Permitted sources only: official legislation, Gazette, public ICSI specimens, public
  listed-company disclosures, Indian Kanoon under its attribution terms.
- No production code changes without tests. One logical change per commit.
- Inspect the repository and report affected files before proposing edits.
- No new dependency without a stated reason.
- No unsupported product, market, legal, or competitor claims.
- If evidence is incomplete, write OPEN or UNVERIFIED. Do not guess.

## Status labels
VERIFIED · PARTIALLY_VERIFIED · UNVERIFIED · INAPPLICABLE · POTENTIAL_ISSUE · STALENESS_WARNING

## Rule output categories
APPLICABLE_DEFECT · POTENTIAL_ISSUE · STALENESS_WARNING · INAPPLICABLE · UNVERIFIED · INFORMATIONAL

## Required output — research task
Question · Sources checked · Evidence found · Evidence quality · Result · Unresolved issues ·
Recommended next action

## Required output — code task
Files changed · Tests added or updated · Commands run · Results · Known limitations · Commit hash

## Repository map
| Path | Contents |
|---|---|
| `checker/` | Verifier, applicability, retrieval, provision graph, amendment parser, as_of, derived_date |
| `checker/section_index.py` | `section_by_number("173")` — number -> corpus ID (97.9% mapped) |
| `checker/legal_ref.py` | Instrument-qualified refs. A provision number is never an identity |
| `checker/mvp_freeze.py` | Pins the 17 hand-verified MVP mappings against silent drift |
| `scripts/run_tests.sh` | Runs all 8 suites with PYTHONPATH set — use this, not bare python3 |
| `checker/ss/` | Secretarial Standards defect scanner + evidenced RULES.md |
| `corpus/companies_act/` | 527 ingested sections, hash-stamped |
| `corpus/testdocs/` | Real + ICSI-specimen documents for scanner validation |
| `corpus/reference/` | SS-1 and SS-2 full text |
| `scripts/` | Ingestion and verification harnesses |
| `docs/` | Architecture, technical plans, retractions |
| `research/TASKS.md` | The task ledger — single source of truth for what is open |

## Verification status
- Corpus cross-render check: **PASS_WITH_DEFECTS**. India Code JSON vs India Code PDF agree
  (median record coverage 1.0000, 456/464 >= 0.99) but **two confirmed defects** — see
  `docs/SOURCE_DEFECTS.md`. Corpus status is NOT_FULLY_VERIFIED.
- Independent-publisher verification: **PENDING**. Both renderings are India Code; a defect in
  their own source is invisible to this check.
- Section index: 464/474 mapped, 17 MVP sections hand-verified. **PDF-derived, not source-confirmed** —
  India Code returned 403 on 21 Aug 2026. Re-verify against the section view when reachable.
- Point-in-time reconstruction: still UNVERIFIED against any external source.

## Known-invalid results — do not cite
- Reconstruction "119/119 EXACT vs as-enacted print" — the reference was the CURRENT consolidation.
  Retracted. Point-in-time reconstruction is UNVERIFIED against any external source.
- "43/43 prior wordings found in the PDF" — circular. The footnotes quoting them are in the file.
- Test A "31/32" is an internal consistency measure, **not** production accuracy.
- ComplyRelax is NOT abandoned. 201 unbroken updates Oct 2020 - Aug 2026.
