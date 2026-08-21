# Claims Ledger

Every externally-usable claim, with its evidence class. Unclassified claims do not ship.

| Claim | Evidence | Class | Safe wording | Unsafe wording |
|---|---|---|---|---|
| Companies Act corpus is complete | 527 sections, 0 fetch failures, 90.6% cross-validated | VERIFIED_PRIMARY | "527 sections ingested from India Code, hash-stamped" | "complete and verified Companies Act database" |
| Amendment ledger is correct | 451 records; 100% of instruments and w.e.f. dates corroborated independently | VERIFIED_PRIMARY | "every amendment instrument and effective date corroborated against an independent rendering" | "100% accurate amendment tracking" |
| Point-in-time reconstruction works | **Benchmark was circular** | **RETRACTED** | *(nothing — say it is unverified)* | "reconstructs any section at any past date" |
| Scanner detects SS defects | Over-fires on real documents; false negatives never measured | UNVERIFIED | "prototype; false-positive rate being measured" | "detects Secretarial Standards defects" |
| Formal defects carry real penalties | 68 ROC adjudication orders | VERIFIED_PRIMARY | "ROC has penalised formal defects — 68 orders, 2021-2026" | "high enforcement risk" — the rate is ~225 orders against ~880,000 filings |
| No defence has ever worked | Named orders: voluntary disclosure, rectification, no-mala-fide, force majeure all rejected | VERIFIED_PRIMARY | quote the orders | generalising beyond s.118 |
| A practitioner stated a superseded rule | 1 comment, 19 Aug 2026, corroborated by 4 secondary articles | **ANECDOTE** | "we observed an instance" | "practitioners routinely state stale rules" |
| ComplyRelax verifies nothing | Checked clause by clause against SS-1/SS-2 | VERIFIED_SECONDARY | "no SS verification mechanism found in its published materials" | "it doesn't work" |
| ComplyRelax is abandoned | 201 unbroken updates | **RETRACTED** | "small, actively shipping, low market presence" | "abandoned" |
| Practising CS pool is 11,460 | ICSI Annual Report 2023-24 | VERIFIED_PRIMARY | cite the AR | — |
| SAM / TAM figures | Built on **CS** market | UNVERIFIED for lawyers | *(do not use)* | any lawyer-market TAM |
| Customer validation | **Zero** corporate lawyers have reviewed the system | UNVERIFIED | "pre-validation prototype" | any claim of lawyer demand |

## Week 1.1 — section number -> section_id index (2026-08-21)

**Claim:** `section_by_number("173")` returns s.173 of the Companies Act 2013.
**Status:** VERIFIED for the 17 MVP sections, by reading each record's text against its title.

| Measure | Value |
|---|---|
| Sections mapped | 464/474 (97.9%) — gate was 95% |
| Duplicate claims | 0 |
| MVP core sections mapped | 12/12, hand-verified |
| MVP extension sections mapped | 5/5, hand-verified |
| Unmapped | 10 |

**What the unmapped 10 are.** Eight are Chapter XXI-A (Producer Companies, s.378F/H/K/Y/ZA/ZG/ZN/ZU),
outside MVP scope. Two (s.51, s.215) scored a single probe hit; the rule requires two, so they are
recorded unmapped rather than guessed. 43 further sections are omitted in the source itself and are
excluded from the denominator, not counted as failures.

**Three source defects found and handled, each of which had produced a silent wrong answer:**
1. A section substituted wholesale carries its heading inside the amendment span (`3[185. Loans to
   directors`), not at a line start. s.185 was missed entirely.
2. The arrangement-of-sections table is repeated at the head of every chapter, so a contents line
   precedes the real body. Anchoring on first match mapped s.3, s.4, s.5, s.56, s.67 to contents
   text. Separated by listing density (contents runs 7-13, bodies 1-3).
3. The PDF reproduces subordinate rules, which renumber from 1. The Act's s.56 is "Transfer and
   transmission of securities"; a rule's s.56 is "Director to intimate DIN". Only the title
   separates them. First-match-wins is unsound on this source.

**Limitation.** The index is built from the India Code full-Act PDF. It inherits any error in that
PDF and in its text extraction. It is not independent verification of the corpus content itself.
