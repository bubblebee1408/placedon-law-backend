# SS-1 / SS-2 defect scanner — real test corpus

Assembled 19-20 Aug 2026. Purpose: break the circularity in `checker/ss/defects.py`, whose regexes
and whose fixtures (`CLEAN`, `DEFECTIVE`) were written by the same author. Until the scanner meets
documents it did not author, its false-positive rate is unknown.

**Everything here is a public document.** No minutes book was obtained; minutes books are not public
and none was sought. The only minutes in this corpus are ICSI's published specimens.

All files are UTF-8 text with a `#`-prefixed provenance header. Strip lines beginning with `#`
before scanning. Source PDFs are under `_raw/` (gitignored via `*.pdf`); the three integrated annual
reports were deleted after extraction because they total ~91 MB and are re-downloadable from the URLs
below.

**Every file below is text-extractable. No document in this corpus requires OCR.**

---

## Count by document type

| Type | Files | Real | Specimen |
|---|---:|---:|---:|
| Minutes specimen (board) | 2 | 0 | 2 |
| Minutes specimen (general) | 3 | 0 | 3 |
| Board meeting notice | 1 | 0 | 1 |
| AGM notice | 10 | 9 | 1 |
| EGM notice | 1 | 0 | 1 |
| Board resolution | 2 | 0 | 2 |
| Board / general meeting outcome filing (Reg 30) | 6 | 6 | 0 |
| Board report extract (SS compliance statement) | 3 | 3 | 0 |
| AGM notice annexure (attendance slip) | 1 | 0 | 1 |
| **Total** | **29** | **18** | **11** |

18 genuinely real documents from 5 distinct listed issuers, spanning 2024-2026.
Minutes extracts quoted in ROC orders: **0 obtained** — see "Attempted and failed" below.

---

## 1. ICSI specimens (`icsi_specimens/`)

Gold standard: ICSI wrote these to comply with its own standards. A well-built scanner should
return near-zero defects. **It does not — see "Calibration run" below.**

Both guidance notes are undated as to edition on their face; the General Meetings note is captioned
"based on Revised SS-2" (revised SS-2 effective 01.10.2017).

| File | Type | Source |
|---|---|---|
| `01_board_meeting_notice_annexII.txt` | board notice | GN Board, Annexure II (para 1.3.1) |
| `02_resolution_by_circulation_annexVI.txt` | board resolution | GN Board, Annexure VI (para 6.2.3) |
| `03_minutes_first_board_meeting_annexVII.txt` | minutes specimen (board) | GN Board, Annexure VII (para 7.3) |
| `04_minutes_subsequent_board_meeting_annexVIII.txt` | minutes specimen (board) | GN Board, Annexure VIII (para 7.3) |
| `05_attendance_slip_annexI.txt` | AGM notice annexure | GN General, Annexure I (para 1.2.10) |
| `06_agm_notice_annexII.txt` | AGM notice | GN General, Annexure II (para 1.2.10) |
| `07_egm_notice_annexIII.txt` | EGM notice | GN General, Annexure III (para 1.2.10) |
| `08_board_resolution_convening_egm_annexIX.txt` | board resolution | GN General, Annexure IX (para 2.2) |
| `09_minutes_agm_annexXVI.txt` | minutes specimen (general) | GN General, Annexure XVI (para 17.3) |
| `10_minutes_egm_annexXVII.txt` | minutes specimen (general) | GN General, Annexure XVII (para 17.3) |
| `11_minutes_adjourned_agm_annexXVIII.txt` | minutes specimen (general) | GN General, Annexure XVIII (para 17.3) |

- Issuer: **ICSI**. Status: **specimen** (blank template, not a filed document).
- GN Board: https://www.icsi.edu/media/webmodules/Final_GuidancenoteonBoardofMeetingpmd.pdf (169pp)
- GN General: https://www.icsi.edu/media/webmodules/Guidance_Note_on_General_Meeting_%28based_on_Revised_SS-2%29.pdf (179pp)

### Staleness found in ICSI's own specimens — CONFIRMED

The brief asked whether the specimen AGM notice still carries the repealed auditor-ratification
requirement. **It does, and so does the specimen AGM minutes.** Two annexures, two occurrences each
(the resolution and the explanatory statement / recital), verbatim:

> "...to hold office from the conclusion of this Annual General Meeting till the conclusion of the
> ____ Annual General Meeting of the company **(subject to ratification of their appointment at
> every AGM)**, at a remuneration of Rs. _______/- ... plus reimbursement of out of pocket expenses
> and **service tax**, as applicable."

- `06_agm_notice_annexII.txt` (Annexure II, Specimen AGM Notice) — GN General p.131
- `09_minutes_agm_annexXVI.txt` (Annexure XVI, Specimen AGM Minutes) — GN General p.163

Two independent staleness markers in one sentence:

1. **Auditor ratification.** The first proviso to s.139(1) Companies Act 2013, which required
   ratification of the auditor's appointment at every AGM, was **omitted by the Companies
   (Amendment) Act 2017, s.40**, notified with effect from **07.05.2018**. A resolution drafted in
   these terms today states a requirement that no longer exists.
2. **"service tax."** Subsumed into GST from 01.07.2017.

Implication for the product, and it cuts both ways: a scanner that flags this language is *correct*
and ICSI's template is stale. This is precisely the version-dating failure mode `checker/ss/RULES.md`
already identifies via the Stanley Lifestyles Regional Director decision — except here the stale
requirement sits inside the standard-setter's own specimen. Do not treat "ICSI specimen returns zero
defects" as the acceptance criterion; on this clause zero defects would be the wrong answer.

---

## 2. Real AGM notices (`agm_notices/`) — 9 documents, 5 issuers, 2024-2026

All real, all filed, all drafted by practising company secretaries. All text-extractable.

| File | Issuer | Size band | Meeting | AGM date | Source |
|---|---|---|---|---|---|
| `tcpl_62nd_agm_notice_2025.txt` | Tata Consumer Products Ltd | Large cap | 62nd AGM | 18 Jun 2025 | IAR 2024-25, pp.447-463 — https://www.tataconsumer.com/sites/g/files/gfwrlq316/files/2025-06/Tata_Consumer_IAR_2024_25.pdf |
| `tcpl_63rd_agm_notice_2026.txt` | Tata Consumer Products Ltd | Large cap | 63rd AGM | 2026 | IAR 2025-26, pp.403-424 — https://www.tataconsumer.com/sites/g/files/gfwrlq316/files/2026-06/INTEGRATED_ANNUAL_REPORT_F_Y_2025_26.pdf |
| `titan_41st_agm_notice_2025.txt` | Titan Company Ltd | Large cap | 41st AGM | 22 Jul 2025 | https://www.titancompany.in/sites/default/files/2025-06/Titan%20Notice%20of%20AGM%20-2024-25.pdf |
| `titan_42nd_agm_notice_2026.txt` | Titan Company Ltd | Large cap | 42nd AGM | 2026 | https://www.titancompany.in/sites/default/files/2026-07/Titan%20AGM%20Notice%202026.pdf |
| `tataelxsi_37th_agm_notice_2026.txt` | Tata Elxsi Ltd | Mid cap | 37th AGM | 2026 | IAR 2025-26, pp.39-98 — https://d1y69b020rytqm.cloudfront.net/PDF/Annual-Reports/June2026/Annual-Report-FY-2025-26.pdf |
| `sonata_29th_agm_notice_2024.txt` | Sonata Software Ltd | Mid cap | 29th AGM | 2024 | https://www.sonata-software.com/sites/default/files/financial-reports/2024-07/NoticeofAGM.pdf |
| `routemobile_20th_agm_notice_2024.txt` | Route Mobile Ltd | Small/mid cap | 20th AGM | 20 Aug 2024 | https://routemobile.com/compliance/2024/Notice-of-AGM-2024.pdf |
| `routemobile_21st_agm_notice_2025.txt` | Route Mobile Ltd | Small/mid cap | 21st AGM | 12 Sep 2025 | https://routemobile.com/compliance/2025/Notice-of-AGM-2025.pdf |
| `routemobile_22nd_agm_notice_2026.txt` | Route Mobile Ltd | Small/mid cap | 22nd AGM | 2 Sep 2026 | https://routemobile.com/wp-content/uploads/2026/08/Notice-of-AGM-2026.pdf |

Two of these are deliberately-kept **adversarial extraction cases**:

- `routemobile_22nd_agm_notice_2026.txt` — source PDF is letter-spaced; extracts as
  `NOTICE  i s  h e r e b y  g i v e n  t h a t  t h e  T w e n ty  S e c o n d`. Every
  `\b`-anchored regex in the scanner misses this text entirely. Real PDFs do this routinely.
- `tataelxsi_37th_agm_notice_2026.txt` — ligature glyphs; "benefit" extracts as "beneﬁt" (U+FB01).

---

## 3. Board resolutions and meeting outcomes (`board_outcomes/`) — 6 real filings + 3 report extracts

### SEBI LODR Regulation 30 "Outcome of Board Meeting" filings — Route Mobile Ltd

These are the **most valuable real documents in the corpus for T1.6**, because Reg 30 requires the
issuer to state the time the board meeting commenced and concluded, in running prose, in real filed
text. This is the only place outside a minutes book where those two values appear publicly.

| File | Board meeting date | Recorded times | Source |
|---|---|---|---|
| `routemobile_outcome_board_meeting_2024-05-29.txt` | 29 May 2024 | commenced 03:00 P.M., concluded 03:15 P.M. | https://routemobile.com/wp-content/uploads/2024/05/Outcome-of-Board-Meeting-May-29-2024.pdf |
| `routemobile_outcome_board_meeting_2025-01-28.txt` | 28 Jan 2025 | commenced 11:40 A.M. (IST), concluded 01:05 P.M. | https://routemobile.com/wp-content/uploads/2025/01/Outcome-of-Board-Meeting-January-28-2025.pdf |
| `routemobile_outcome_board_meeting_2025-11-03.txt` | 3 Nov 2025 | commenced 9:30 P.M., concluded 11:10 P.M. | https://routemobile.com/wp-content/uploads/2025/11/Outcome-of-Board-Meeting-November-3-2025.pdf |
| `routemobile_outcome_board_meeting_2026-05-07.txt` | 7 May 2026 | commenced 6:20 P.M. IST, concluded 8:50 P.M. | https://routemobile.com/wp-content/uploads/2026/05/Outcome-of-Board-Meeting-May-07-2026.pdf |

`...2026-05-07.txt` is an **adversarial case for the conclusion check**: the attached auditor's report
contains "Conclude on the appropriateness of Board of Directors' use of the going concern basis",
an unrelated use of the verb the `_CONCLUDED` pattern looks for.

### Outcome of AGM filings — Sonata Software Ltd

| File | Meeting | Source |
|---|---|---|
| `sonata_outcome_of_agm_2025.txt` | 30th AGM, 2025 | https://www.sonata-software.com/sites/default/files/financial-reports/2025-08/outcomeofagm2025.pdf |
| `sonata_outcome_of_agm_2026.txt` | 31st AGM, 2026 | https://www.sonata-software.com/sites/default/files/financial-reports/2026-07/outcomeofagm.pdf |

### Board report SS-compliance statements — tests T2.1

| File | Issuer | FY | Wording |
|---|---|---|---|
| `tcpl_board_report_ss_statement_2024_25.txt` | Tata Consumer | 2024-25 | "has complied with all the applicable Secretarial Standards" |
| `tcpl_board_report_ss_statement_2025_26.txt` | Tata Consumer | 2025-26 | "has complied with all the applicable Secretarial Standards on Board Meetings and General Meetings" |
| `tataelxsi_board_report_ss_statement_2025_26.txt` | Tata Elxsi | 2025-26 | "has **devised proper systems to ensure compliance** with ... all applicable Secretarial Standards" |

Deliberate contrast set. Tata Elxsi asserts adequate *systems*, not actual *compliance*. A T2.1 check
keyed to "has complied" passes the first two and misses the third, though all three are the standard
s.134 statement. Three real phrasings of one statement is the minimum needed to write that check
honestly.

---

## 4. Minutes (`minutes_extracts/`) — empty

Minutes books are not public and none was sought. The corpus's only minutes are ICSI's five
specimens. No verbatim minutes extract from an ROC adjudication order was obtained — see below.

---

## Attempted and failed

| Source | Attempt | Result |
|---|---|---|
| MCA adjudication orders (for minutes quoted verbatim in s.118 orders) | `mca.gov.in/.../adjudication-orders.html` | **HTTP 403.** MCA blocks automated fetches. The 68-order corpus behind `checker/ss/RULES.md` is not in this repo or in `placedon-law-research`, so no order text was available locally either. This is the single largest gap: minutes extracts inside ROC orders are the only realistic source of *defective* real minutes, and the corpus is therefore all-compliant, which cannot measure false negatives. |
| WebSearch | — | Session budget (200 calls) already exhausted before this task began. All discovery was done by direct URL and by following links off investor-relations pages. |
| DuckDuckGo (`html.` and `lite.`), Mojeek | direct HTTP | HTTP 202 challenge / HTTP 403. No search-engine fallback available. |
| Infosys IR | `infosys.com/investors/reports-filings/annual-report.html` | HTTP 403 |
| Happiest Minds IR | `happiestminds.com/investors/` | HTTP 403 |
| CEAT IR | `ceat.com/investors/` | HTTP 406 |
| Godrej Consumer IR | `godrejcp.com/investors` | HTTP 403 |
| Kirloskar Brothers IR | `kirloskarpumps.com/investors` | HTTP 503 |
| Bank of Baroda IR | `bankofbaroda.in/investors` -> `bankofbaroda.bank.in/investors` | 301 then HTTP 404. No PSU-bank notice obtained; the real-document set is all private-sector. |
| Dabur IR notices | `dabur.com/investor/investor-information/notices` | Page reached, but the notice list is loaded by script and exposes no PDF URLs to a non-JS fetch. |
| Voltas / Trent / Cyient / Tanla / Balaji Amines IR | various | HTTP 404 on every guessed path. |

---

## Calibration run — what the corpus found

`checker/ss/defects.py:scan()` was run over 18 documents (5 ICSI minutes specimens, 4 real Reg 30
board-meeting outcomes, 9 real AGM notices). AGM notices are out-of-domain for a minutes scanner and
are included to measure over-firing, not to be judged.

**Headline: T1.6a fires DEFECT on 18 of 18 documents, including all five of ICSI's own specimen
minutes. On this corpus its false-positive rate is 100%.**

| Check | Behaviour on real / specimen text | Diagnosis |
|---|---|---|
| **T1.6a** serial number | DEFECT on 18/18 | `_SERIAL` requires `Meeting No: 14` phrasing — the phrasing used in the author's own `CLEAN` fixture. Real Indian practice writes an ordinal in the title: "the 62nd Annual General Meeting", "the Twenty First ("21st") Annual General Meeting", "Minutes of the .......... Meeting". None matches. |
| **T1.6b** commencement | PASS on all 4 Reg 30 outcomes (correct). **False PASS on 6 AGM notices** | On notices it matched "The Remote e-Voting period **commences** on Saturday, June 14, 2025, at **9:00 a.m.**" — the e-voting window, not the meeting. Same-sentence co-occurrence of a `commenc\w+` verb and any clock time is too weak a test. |
| **T1.6c** conclusion | PASS on all 4 Reg 30 outcomes (correct) | Works on real filled text. Confirmed against four independent filings including a single-digit hour ("9:30 P.M."). |
| **T1.7** place of signing | PASS on 8 AGM notices, all via evidence `'place of'` | `_PLACE_SIGNED` matches the bare word "place" anywhere in prose. Passing a document that has no signing block at all is a **false PASS on a penalty-backed check** (Wind World, Sany). |
| **T1.8** tense | DEFECT on 15/18 including ICSI specimens | `_FIRST_PERSON` matches the roman-numeral list marker "i" — evidence on Titan is literally `'iii)  The remote e-Voting period commences...'`. Every Indian corporate document numbers clauses (i), (ii), (iii). Advisory-only, so it does not become a violation, but it is noise on essentially every document. |
| **T1.4a** date of entry | DEFECT on all real documents | Correct and uninformative: entry date exists only in the minutes book, never in a notice or a Reg 30 filing. |
| **T1.5** signatory | PASS on 18/18 | No false positives. Unexercised in the negative direction — no real document in the corpus contains an "on behalf of the Chairman" signature. |
| **C.quorum** | PASS on all minutes specimens, DEFECT on all Reg 30 outcomes | Correct in both directions. Reg 30 outcome letters genuinely do not recite quorum. |

Both possibilities the brief raised turned out to be live, and they are separable:

- **The scanner over-fires.** T1.6a, T1.7 and T1.8 fail against documents drafted by ICSI itself and
  by five listed companies' company secretaries. These are scanner defects, not document defects.
- **The specimen is stale.** Independently confirmed, on the auditor-ratification clause, in two
  ICSI annexures.

A third finding the brief did not anticipate: **the ICSI specimens cannot validate the value-level
checks at all.** They are blank templates — the conclusion line reads `the Meeting concluded at
.... (Time)`, so `_TIME` correctly finds no clock time and T1.6b/T1.6c fire. That is a template
artifact, not a defect and not a scanner bug. The specimens can only test whether a *field is
present*; only the real Reg 30 filings can test whether a *value parses*. Both document classes are
needed, which is why both are in this corpus.

---

## What each check can and cannot be tested with

| Check | Best documents here | Notes |
|---|---|---|
| T1.1 pages consecutively numbered across the book | **none — untestable** | See below. |
| T1.2 every page initialled by Chairman | **none — untestable** | Physical-book property. |
| T1.3 blank pages scored out | **none — untestable** | Physical-book property. |
| T1.4a date of entry recorded | ICSI Annexures VII, VIII (both end "Entered on") | Only specimens carry the field. |
| T1.4b entry within 30 days | **none** | Needs two dates that no public document publishes together. Correctly returns NEEDS_BOOK. |
| T1.5 correct signatory | ICSI Annexures VII, VIII, XVI | No real negative case available. |
| T1.6a serial number | all 18 | Strongest evidence in the corpus; currently 100% FP. |
| T1.6b / T1.6c commencement and conclusion | **the 4 Route Mobile Reg 30 outcomes** | The only real filed text stating both times. Use `...2026-05-07.txt` for the "Conclude on the appropriateness" false-positive trap. |
| T1.7 place of signing | ICSI Annexures VII, VIII (`Place ......`); Reg 30 outcomes as true negatives | Real AGM notices expose the spurious "place of" match. |
| T2.1 board report SS statement | the 3 SS-statement extracts | Tata Elxsi is the hedged-wording case. |
| T2.2 attendance register | `05_attendance_slip_annexI.txt` | Members' attendance slip, not the SS-1 4.1 board attendance register — related but not the same instrument. |
| T3.1 special business + explanatory statement | all 9 real AGM notices | Every one carries an s.102 explanatory statement. Highest-value real-document check in the corpus. |
| T3.2 attendance slip + proxy form with notice | the 9 real AGM notices; ICSI Annexure I | Note most 2024-26 notices are VC/OAVM, where proxies are not applicable — the check must be conditional on meeting mode or it will over-fire on every modern notice. |
| T3.3 notice signed by director/authorised person | all 9 real AGM notices | e.g. Tata Consumer signed by Delnaz Dara Harda, Company Secretary, ACS 73704. |
| T3.5 21 clear days | all 9 real AGM notices | Notice date and meeting date both present. |
| T3.7 AGM within statutory deadline | all 9 real AGM notices | FY-end and AGM date both present. |
| T3.8 auditor attendance at AGM | `09_minutes_agm_annexXVI.txt`; Sonata outcome-of-AGM filings | |

### Page numbering cannot be tested from a PDF — at all

T1.1 (consecutive pagination across the whole minutes book), T1.2 (Chairman's initials on every page)
and T1.3 (blank pages scored out and initialled) are properties of a **bound physical minutes book**.
They are not properties of any document in this corpus and cannot be made testable by adding more
PDFs. A PDF's page numbers describe that PDF, not the book; and the penalised defect in Rosmerta
Technologies was numbering that *restarted each financial year* across a book spanning years, which
no single extracted document can exhibit.

`defects.py` already handles this correctly by returning `NEEDS_BOOK` rather than guessing, and that
is the right behaviour — but it means **T1.1-T1.3, ~24 of the 68 orders behind `RULES.md` and the
single highest-frequency defect class, are permanently outside the reach of any document scanner.**
Validating them requires physical inspection or a photograph of the book. That boundary should be
stated to a professional up front, not discovered by them.
