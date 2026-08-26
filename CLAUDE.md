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
| `scripts/verify_document.py` | Is this PDF real? Cryptographic signature check, CCA India |
| `scripts/verify_section_index.py` | Our number->id map vs India Code's own API |
| `checker/robots.py` | Robots + TLS enforcement in the fetch path; fails closed |
| `checker/corroborate.py` | Prior wording vs the amending Act — the non-circular check |
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
- Section index: **474/517 entries mapped, 0 live sections unresolved.** The remaining 43 are
  provisions the legislature omitted (s.11; ss.253-269, omitted by the IBC w.e.f. 15-11-2016),
  which resolve to None by design. 10 sections our PDF parse left ambiguous — s.51 and nine
  Producer Company provisions — were resolved from India Code's API and carry
  `confidence: source-confirmed` (`scripts/resolve_missing_sections.py`).
- MVP sections verified against India Code's own REST API: 12/12, 0 mismatches
  (`scripts/verify_section_index.py`). The checker also reports **STALE_TEXT** — holding live
  text for a provision the source marks omitted, i.e. serving repealed law as current.
- **India Code moved domain.** `indiacode.nic.in` 403s everything; the live host is
  **`indiacode.gov.in`**, running DSpace with an open REST API (no key, no auth) exposing
  `dc.identifier.section_number`, `section_id`, `section_footnote`, `act_name`. The 403 that
  blocked us since 21 Aug was a dead domain, not a block. Any hardcoded `.nic.in` URL is dead.
- Point-in-time reconstruction: **boundary behaviour proved** on s.177, s.447 and s.35 —
  6/6 boundaries, text changes across each, effective dates inclusive
  (`scripts/prove_temporal.py`, `docs/TEMPORAL_PROOF.md`). EXACT there rests on 5 insertions
  (recoverable by deletion, no witness needed) and 3 substitutions (single-sourced footnotes).
- **SD-003: 120 amendment spans carry unbalanced markup.** s.96 is one — it cannot be
  reconstructed before 13-6-2018 at all. Two thirds of amended sections are affected.
- Section-level reconstruction of **substituted** spans still UNVERIFIED.
  But prior wording is now independently corroborated for the first time: 24 amended
  spans matched against the amending Acts themselves on Indian Kanoon, **0 conflicts**;
  21/24 where the instrument is held. See `docs/CORROBORATION.md`. This corroborates
  individual spans, not whole sections — the distinction the retracted claims missed.
- Indian Kanoon does not host The Companies (Amendment) Act, 2019, so claims resting
  on Act 22 of 2019 have no witness on that source (9 of 16 unresolved cases).

## Known-invalid results — do not cite
- Reconstruction "119/119 EXACT vs as-enacted print" — the reference was the CURRENT consolidation.
  Retracted. Point-in-time reconstruction is UNVERIFIED against any external source.
- "43/43 prior wordings found in the PDF" — circular. The footnotes quoting them are in the file.
- Test A "31/32" is an internal consistency measure, **not** production accuracy.
- ComplyRelax is NOT abandoned. 201 unbroken updates Oct 2020 - Aug 2026.
