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

## Week 1.1 gate — PASS (2026-08-21)

464/474 (97.9%) mapped · 0 duplicates · 17/17 MVP sections hand-verified · 8 suites green.
Denominator is 474: the 43 sections omitted in the source are excluded, not counted as failures.
This denominator is fixed and must not be quietly restated later.

**Attempted and failed: independent verification.** India Code publishes a section view whose URL
carries both number and ID (`sectionId=49099&sectionno=173`), which would confirm the mapping from
the source rather than from my inference. It returned HTTP 403 and timed out on direct request on
21 Aug 2026. Project rules forbid working around the WAF, so this was not pursued further. A
third-party document quotes that URL with a value agreeing with the mapping derived here; agreement
between two independent derivations is corroboration, **not** verification, and is not recorded as
such. The index remains PDF-derived and inherits any defect in that PDF.

**Follow-up when India Code is reachable:** fetch the section view for the 17 MVP sections and
compare against `_index.json`. That would upgrade the index from inferred to source-confirmed.

## Week 2.1 — acquisition of the Meetings of Board Rules 2014: NOT ACQUIRED (2026-08-21)

**Outcome: BLOCKED — loop halted at T1 per runbook. No unofficial mirror substituted.**

| Host | Result | Reading |
|---|---|---|
| `upload.indiacode.nic.in` | ECONNREFUSED (164.100.94.56) | Host down — not blocking us |
| `www.indiacode.nic.in` `/bitstream/*.pdf` | 200 | Static assets serve |
| `www.indiacode.nic.in` `/handle/`, `/oai/`, `/rest/`, sitemap | timeout | **All dynamic paths dead** |
| `www.mca.gov.in` | 403 | Blocked |
| `egazette.gov.in` | 200 | Reachable; stateful search form |

**Why this blocks acquisition.** India Code serves the document from a static bitstream path, but
the *path is discovered* through dynamic pages, and those are down. The document is very likely
still there; we cannot currently find its address. This is the same static/dynamic split seen in
Week 1, now confirmed twice.

**Not done, deliberately:** no unofficial mirror (`ca2013.com`, `vlex`, `taxguru`, `thc.nic.in`)
was used. Their fidelity to the gazetted text is unestablished, and an unofficial copy that is 99%
right is worse than none — it is indistinguishable from the real thing at the point of use. No WAF
evasion, no brute-forcing of bitstream paths.

**Recorded as `UNREACHABLE`, not `BLOCKED`.** The distinction is load-bearing: ECONNREFUSED and
timeouts mean infrastructure failure, and dynamic India Code was working on 20 Aug. This is
intermittent and should be retried, not treated as withdrawal of the document.

### Incidental finding — the Week 1 artifact is authentic

The Act PDF was re-fetched from India Code today and is **byte-identical** to the stored copy:
`d6e286d2a3feec89a7d432a5a572e91af9f0135411b03e57f72b7a8ef72139af`. The artifact underpinning the
section index is confirmed unmodified since retrieval on 19 Aug. This does **not** upgrade the
index's evidence state — it is the same single source, re-read, not an independent one.

### Next action

1. Retry India Code dynamic paths (intermittent; worked 20 Aug).
2. If still down, a human can retrieve the Rules from eGazette — notified by G.S.R. dated
   31 Mar 2014 — via the search form, and drop the PDF into `corpus/sources/`. **Verify the
   instrument identity on download**: principal Rules vs a later amendment rule is exactly the
   confusion this project must not make.

### Week 2.1 retry, 16:36 IST — no change

India Code dynamic paths still time out; `upload.indiacode.nic.in` still refuses connections;
static `/bitstream/*.pdf` still serves 200. Web-search discovery of the official bitstream address
was unavailable (session search budget exhausted, 200/200). Automated acquisition is out of options.

**Loop stopped.** Further unattended re-probing would spend budget to learn nothing. Acquisition now
needs either India Code to recover or a human download.

**Handoff built:** `scripts/acquire_rules.py` verifies, hashes, stores and prints the provenance
record for a downloaded PDF. It REFUSES a file whose identity it cannot confirm, and specifically
refuses an *Amendment Rules* document in place of the principal 2014 Rules — near-identical titles,
different instruments. 7/7 tests.

    python3 scripts/acquire_rules.py ~/Downloads/<file>.pdf

## Week 2.1 — ACQUIRED (2026-08-21)

**The Companies (Meetings of Board and its Powers) Rules, 2014 — principal Rules.**
`corpus/sources/companies_meetings_board_powers_rules_2014.pdf`, sha256 `b8b2e01b…67c`, 22 pages.
Classified `VERIFIED_PRINCIPAL` by `scripts/acquire_rules.py`.

### How, after every India Code route failed

India Code stayed blocked throughout (four dynamic endpoints 403, file host down). The document
came from **eGazette's own notification-date search** — searched 31 MAR 2014, which returned
content id **159201**, served from the static `WriteReadData` path under that id. No mirror, no WAF
evasion, no brute-forced identifiers: the id came from the Gazette's own search results.

The earlier judgement that eGazette was "too fragile to script unattended" was wrong. It took one
correction to find: the date field rejects `31/03/2014` with an HTTP 500 and accepts `31 MAR 2014`.

### The lead is now confirmed from the document

`G.S.R. 240(E)`, `31st March, 2014` — previously an unverified third-party claim, held deliberately
as a lead. The acquired gazette **states both in its own text**. `PRINCIPAL_RULES_LEAD` moves
`UNFETCHED_CORROBORATION → CORROBORATED`, naming the artifact that resolved it. The *amendment*
list in that record was never checked and remains a lead.

### Two false negatives the guard produced, both corrected

1. **`CORRUPT_OR_UNREADABLE`** — `pdftotext` is not installed on this machine. The document was
   perfectly readable. A guard reporting a property of the toolchain as a property of the evidence
   is worse than no guard, because it reads as a fact about the law. Fixed by
   `checker/pdf_text.py`, a dependency-free reader, now the PRIMARY path.
2. **`REJECTED_AMENDMENT`** — triggered by `"in the said rules"`, which appears in the *definitions
   clause of the principal Rules*: "…shall have the same meanings respectively assigned to them in
   the Act or in the said Rules." Ordinary cross-reference, not an amendment operation. The pattern
   now requires an operative direction ("In the said rules, in rule 4, …"). Separately, extraction
   splits the title as "Meetings of Board **an d** its Powers", so the title match now tolerates the
   known intra-word spacing artifact.

Both were corrected against the document's own evidence — `"further to amend"` absent,
`"Short title and commencement"` present — not by relaxing the guard to obtain a pass.

### Status

`human_reviewed = False`. `can_promote()` refuses VERIFIED until a person reads it. **Acquisition
is custody, not review.** Nothing has been ingested into the corpus; that is Week 2.2.
