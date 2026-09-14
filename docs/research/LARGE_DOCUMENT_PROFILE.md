# R5 — Large Indian corporate documents: a measured profile

Written 2026-09-14 for PLAN_11 Track R (task R5). Feeds `PLAN_12_DOCUMENT_INTAKE_ARCHITECTURE.md`.

**Markers.**
- **MEASURED**: I downloaded one public file from the URL shown and measured it locally with PyMuPDF 1.28.2 on 2026-09-14. Byte counts come from curl's `size_download` and match `os.path.getsize`.
- **MEASURED-local**: a file already in this repo, measured the same way.
- **SOURCED**: stated in a document or page I opened, with its URL.
- **INFERRED**: my own reasoning, labelled as such.
- **UNVERIFIED**: seen only in a search-result snippet.

**Sampling discipline.** Six external documents, each downloaded once to the session scratchpad and not added to the repo. That is a hand-picked sample, not a crawl. Robots.txt was checked on each host first; see "Sources checked". Nothing sits behind a login.

**Heuristics used (and their limits).**
- **"Textless page":** the page yields fewer than 50 characters from `page.get_text()`. That is a proxy for "scanned image with no text layer". I ran no OCR, so a textless page is scanned or blank. For every textless range reported below, I confirmed that its first page carries an embedded image.
- **"Garbled text layer":** fewer than 3% common English stopwords among alphabetic tokens, or more than 20 Latin-Extended-B/Greek glyphs. I checked the flagged pages by eye. The flags on TCPL were false positives (brand wordmarks, a BSI assurance letter). The flags on IBREL were real.
- **Table counts:** PyMuPDF `find_tables()`. It is known to undercount borderless tables, so treat these as lower bounds.

---

## Question

1. **(a) Schemes of arrangement and amalgamation (Companies Act 2013 ss.230–232).** As filed publicly by listed companies (NSE/BSE disclosures, company sites, public NCLT orders), what do they look like? Page counts, structure, annexures (valuation report, fairness opinion, share exchange ratio, financials), and scanned vs text-layer pages.
2. **(b) Ind AS financial statements in annual reports.** Page counts, table density, notes structure.
3. **(c) Other bulk-review documents a diligence lawyer sees.**
4. **What is already held** in `corpus/testdocs/`, with sizes?
5. **What PLAN_12 intake must be sized for** on this evidence.

## Sources checked

| Source | Robots.txt result (fetched 2026-09-14) | Used? |
|---|---|---|
| https://www.nseindia.com/robots.txt | `Allow: /`, `Disallow: /market-data-test` | host policy noted |
| https://nsearchives.nseindia.com/robots.txt | No robots file: the host returned an HTML error page | yes, 2 files. INFERRED: no robots file means no robots restriction. `checker/robots.py` behaviour on a missing robots file was not checked. |
| https://www.bseindia.com/robots.txt | Returned the site's HTML app shell, not a robots file; directives not determinable | **no**. BSE `AttachLive` PDFs found by search were not downloaded (fail closed). |
| https://www.sebi.gov.in/robots.txt | No response, twice (curl HTTP 000) | **no**. SEBI-hosted DRHP/RHP PDFs found by search were not downloaded (fail closed). |
| https://nclt.gov.in/robots.txt | Disallows only `/core/`, `/profiles/`, `/README.txt` | yes, 1 file (`gen_pdf.php`) |
| https://www.vedantapower.com/robots.txt | Disallows only `/wp-admin/` | yes, 1 file |
| https://embassyindia.com/robots.txt | Disallows only `/wp-admin/` | yes, 1 file |
| https://www.tataconsumer.com/robots.txt | Disallows `/core/`, `/profiles/`, `/admin/`, and similar; `/sites/...` not disallowed | yes, 1 file |
| https://d1y69b020rytqm.cloudfront.net/robots.txt (Tata Elxsi AR host) | HTTP 403 | **no**; relied on existing MANIFEST page range only |
| Web searches (4 queries: scheme filings with valuation and fairness annexures; NCLT sanction orders; NCLT-convened meeting notices; 2026 DRHPs) | n/a | used only to find candidate URLs; nothing is claimed from snippets except where marked UNVERIFIED |
| `corpus/testdocs/` and `corpus/testdocs/MANIFEST.md` (local) | n/a | yes |

## Evidence found

### E-A. Sampled external documents: headline measurements

| id | Issuer | Document type | URL | Bytes | PDF pages | Text layer | Marker |
|---|---|---|---|---|---|---|---|
| A1 | Indiabulls Real Estate Ltd (IBREL); scheme with NAM Estates Pvt Ltd and Embassy One Commercial Property Developments Pvt Ltd | Notice of NCLT-convened equity shareholders' meeting, with explanatory statement, the scheme and all annexures (ss.230–232) | https://embassyindia.com/wp-content/uploads/2025/12/NCLT_Meeting_Notice_Explanatory_Stmt_Annexures_Equity_shareholders-1.pdf | 18,971,025 | **512** | **Mixed.** 106 of 512 pages (20.7%) textless and carrying images. At least 17 further pages have a *corrupted* text layer (see E-C). | MEASURED |
| A2 | Tata Motors Ltd (demerger scheme, NCLT Mumbai Bench-I) | NCLT order, C.P.(CAA)/139/MB/2025 in C.A.(CAA)/61/MB/2025 | https://nclt.gov.in/gen_pdf.php?filepath=%2FEfile_Document%2Fncltdoc%2Fcasedoc%2F2709138071692025%2F04%2FOrder-Challenge%2F04_order-Challange_004_175612431034595096668ac54969a494.pdf | 249,424 | **13** | **Yes**, all 13 pages; no images; producer "Acrobat PDFMaker 17 for Word" | MEASURED |
| A3 | Vedanta group (Talwandi Sabo Power Ltd, Malco Energy Ltd, Vedanta Aluminium Metal Ltd and others; NCLT Mumbai Court-V) | NCLT order sanctioning scheme, C.P.(CAA)/254(MB)2025 in C.A.(CAA)/220(MB)2024 | https://www.vedantapower.com/wp-content/uploads/2026/04/NCLT-Order-dated-January-09-2026-sanctioning-Scheme-of-Arrangement-for-TSPL.pdf | 311,487 | **40** (cover plus "Page 1 of 39" onward) | **Yes**, all 40 pages; no images; born-digital from Word | MEASURED |
| A4 | Birla Cable Ltd | Regulation 30 LODR intimation of a scheme of amalgamation, 21 Mar 2026. It names the registered valuers and gives the rationale; **the scheme and annexures are not attached** | https://nsearchives.nseindia.com/corporate/BIRLACABLE_21032026191306_SchemeofArrangement.pdf | 1,130,618 | **5** | **Yes**, all 5 pages; 1 page has an image | MEASURED |
| B1 | Tata Consumer Products Ltd (TCPL) | Integrated Annual Report 2024-25: standalone and consolidated Ind AS statements plus the AGM notice | https://www.tataconsumer.com/sites/g/files/gfwrlq316/files/2025-06/Tata_Consumer_IAR_2024_25.pdf | **39,425,911** | **466** | **Yes.** 2 textless pages (464–465; the document's own outline labels p.465 "Blank Page"); 126 pages carry images; producer InDesign | MEASURED |
| C1 | SRIT India Ltd | Draft Red Herring Prospectus (SEBI ICDR) | https://nsearchives.nseindia.com/corporate/Registration_30012026232953_SRITDRHPFinal.pdf | 6,725,970 | **470** | **Yes.** 1 textless page (p.6); 21 pages with images; producer Word 2019; **no bookmarks/outline** | MEASURED |

### E-B. Structure of a full scheme bundle (A1)

The bundle's own index (PDF pp.1–2) gives these page ranges. I checked that its printed page numbers match PDF page indices: p.1 is printed "1", and the scanned block starts exactly at the index's p.98.

| id | Component | Pages | Count | Share of 512 | Text layer, measured per page | Marker |
|---|---|---|---|---|---|---|
| B-1 | Notice of NCLT-convened meeting (ss.230–232 read with the CAA Rules 2016) | 1–11 | 11 | 2.1% | text | SOURCED (index) / MEASURED (layer) |
| B-2 | Explanatory statement, s.230(3) read with s.102 | 12–37 | 26 | 5.1% | text | same |
| B-3 | **The scheme itself** | 38–97 | 60 | 11.7% | text | same |
| B-4 | Valuation report(s), 18 Aug 2020 (N S Kumar & Co.; Niranjan Kumar, RV; BDO Valuation Advisory LLP, RV), incl. "Fair Equity Share Swap Ratio Report" and valuation annexures | 98–189 | 92 | 18.0% | **Mixed.** pp.98–146 (49 pp) textless; pp.147–189 (the BDO report and annexures) text | same |
| B-5 | Fairness opinion, 18 Aug 2020 (O3 Capital Global Advisory Pvt Ltd, SEBI Cat-I merchant banker) | 190–196 | 7 | 1.4% | text | same |
| B-6 | BSE observation letter, 19 Feb 2021 | 197–198 | 2 | — | text | same |
| B-7 | NSE observation letter, 23 Feb 2021 | 199–200 | 2 | — | text | same |
| B-8 | CCI order, 24 Feb 2021 | 201–206 | 6 | — | text | same |
| B-9 | Board reports under s.232(2)(c) (three companies) | 207–220 | 14 | 2.7% | **Mixed.** pp.207–210 textless | same |
| B-10 | Complaints report to BSE/NSE | 221–222 | 2 | — | **textless** | same |
| B-11 | Audited annual accounts FY 2020-21 of all three companies | 223–432 | **210** | **41.0%** | **Mixed.** pp.273–294 (22 pp) textless, between NAM Estates' notes (p.272) and IBREL's standalone auditor's report (p.295) | same |
| B-12 | Unaudited financial results of IBREL to 30 Sep 2021 | 433–444 | 12 | 2.3% | **textless (all 12)** | same |
| B-13 | Unaudited balance sheets / management accounts of transferor companies to 30 Sep 2021 | 445–491 | 47 | 9.2% | text, **but corrupted on ≥15 pages** (E-C) | same |
| B-14 | Abridged-prospectus-format information (SEBI circular dated 22 Dec 2020) | 492–512 | 21 | 4.1% | **Mixed.** pp.494–503 and 506–512 textless; pp.493 and 505 corrupted | same |

The bundle's own p.1 says the meeting was convened by NCLT Chandigarh Bench order dated 23 Dec 2021, for 12 Feb 2022, SOURCED from A1. **The document is from 2022**, even though the host path is dated 2025/12. INFERRED: its structure reflects the CAA Rules 2016 and the SEBI scheme regime as of 2020–21; a 2026 bundle may differ in annexure list.

**Derived shares (INFERRED arithmetic on the rows above):**
- Financial statements and results (B-11 + B-12 + B-13) = 269 of 512 pages (**52.5%**).
- Valuation and fairness (B-4 + B-5) = 99 pages (19.3%).
- The scheme text proper is 60 pages (11.7%).
- The instrument the Companies Act ss.230–232 actually governs is about one-eighth of the file a reviewer receives.

### E-C. Text-layer quality defects (A1): a text layer is not usable text

| id | Claim | Marker | URL |
|---|---|---|---|
| C-1 | p.445 has a text layer in which the units header is Caesar-shifted by 3 letters. The line reads `DOODPRXQWVLQ₹WKRXVDQGVXQOHVVRWKHUZLVHVWDWHG`, which decodes to "allamountsin₹thousandsunlessotherwisestated". The figures on the page (e.g. "Investment property 5 8,06,470.99") extract correctly. | MEASURED (decoding INFERRED) | A1 URL |
| C-2 | pp.460–473 (14 pages, notes to consolidated financial statements to 30 Sep 2021) carry 100–214 stray Latin-Extended/Greek glyphs per page (e.g. `ȋ᲏Ȍ` where a units bracket is expected) alongside readable text. | MEASURED | A1 URL |
| C-3 | pp.493 and 505 begin `ZeƉorƚ >iŵiƚaƚioŶƐ͗` ("Report Limitations:") with a readable body. INFERRED: a broken font ToUnicode map. | MEASURED | A1 URL |
| C-4 | The "garbled" heuristic flagged 14 pages; C-1 and C-3 were found by eye and missed by it. The true count of corrupted pages is therefore **≥17 and not fully measured**. | MEASURED (lower bound) | A1 URL |
| C-5 | Embedded scan resolution on the first page of each textless range. INFERRED arithmetic: dpi = image px ÷ (page pt ÷ 72). | MEASURED px; INFERRED dpi | A1 URL |

Scan resolutions for C-5:

| Pages | Image size (px) | Effective dpi | Note |
|---|---|---|---|
| 98 | 703×994 | ≈85 | |
| 207 | 2338×1653 | ≈200–280 | landscape image on a portrait page |
| 221 | 2111×2984 | ≈256 | |
| 273 | 785×1113 | ≈95 | |
| 433 | 777×1005 | ≈94 | |
| 494 | 1117×1577 | ≈135 | |
| 506 | 745×1053 | ≈90 | |

**Most scanned blocks are below 100 dpi.**

### E-D. NCLT orders (A2, A3)

| id | Claim | Marker | URL |
|---|---|---|---|
| D-1 | Both public NCLT orders sampled are short and born-digital: 13 and 40 pages, 100% text layer, no images. | MEASURED | A2, A3 URLs |
| D-2 | A3 pp.15–34 (20 of 40 pages) are a table headed "Paragraph number of the Report / Observations from …". They reproduce regulator/RD observations and the company's responses. Half the order is tabular. | MEASURED (headings via text extraction) | A3 URL |
| D-3 | A2 repeats a running header ("IN THE NATIONAL COMPANY LAW TRIBUNAL, MUMBAI BENCH-1 C.P.(CAA) NO. 139/MB/2025 …") on every page. A3 repeats "C.P.(CAA)/MB/254/2025 … Page n of 39". | MEASURED | A2, A3 URLs |
| D-4 | The A3 order date (9 Jan 2026) comes from the file name only; I did not read it in the order text. | UNVERIFIED | A3 URL |
| D-5 | Search snippets say the A2 order is dated 25 Aug 2025 and concerns TML Commercial Vehicles Ltd / Tata Motors Passenger Vehicles Ltd. I did not confirm this from the order text. | UNVERIFIED | A2 URL |

### E-E. Ind AS annual report (B1)

| id | Claim | Marker | URL |
|---|---|---|---|
| E-1 | 466 PDF pages; 39.4 MB. | MEASURED | B1 URL |
| E-2 | Page geometry: 334 pages at 594×738 pt; **130 pages at 1188×738 pt** (two-up spreads, PDF pp.4–133); 1 page at 1480 pt (p.3, cover with flap); 1 at 886 pt (p.2). | MEASURED | B1 URL |
| E-3 | Because of the spreads, **PDF page index ≠ printed page number** for the front section. INFERRED: printed page count is roughly 466 + 130 ≈ 596. The printed-to-PDF mapping was not measured. | INFERRED | B1 URL |
| E-4 | Standalone Ind AS block: Independent Auditor's Report on the Standalone Financial Statements starts at PDF p.291. Consolidated block: its auditor's report starts at p.361. The AGM notice starts at p.447. Blocks by boundary: standalone ≈ pp.291–360 (70 pp), consolidated ≈ pp.361–446 (86 pp). Together ≈156 pp, **≈33% of the file**. | MEASURED (boundary headings); block spans INFERRED | B1 URL |
| E-5 | AGM notice pp.447–463 matches the page range already recorded in `corpus/testdocs/MANIFEST.md`. | MEASURED; consistent with MANIFEST | B1 URL |
| E-6 | Numeric-token density (tokens matching a number pattern): narrative pp.10–100 mean **2.8%**; standalone FS **13.5%**; consolidated FS **14.5%**. | MEASURED | B1 URL |
| E-7 | `find_tables()` on every 7th page: standalone found 28 tables / 153 rows on 10 sampled pages; consolidated found 24 tables / 167 rows on 13. That is about 2–3 detected tables per FS page, a lower bound (borderless tables undercount). | MEASURED (heuristic) | B1 URL |
| E-8 | Standalone notes run to at least note 43 (regex on numbered headings). The exact note count was not established. | INFERRED (heuristic, low confidence) | B1 URL |
| E-9 | PDF outline: 1 entry only ("Blank Page"). **No usable bookmarks** for section navigation. | MEASURED | B1 URL |
| E-10 | Garble-heuristic flags on pp.1–2 and 278–283 were false positives: brand wordmark repetition and a BSI assurance statement. The TCPL text layer is clean. | MEASURED (manual check) | B1 URL |

### E-F. Other bulk-review candidates (c)

| id | Claim | Marker | URL |
|---|---|---|---|
| F-1 | A 2026 SME/mainboard DRHP (C1) is 470 pages / 6.7 MB, 469 of 470 pages text-layered, with no outline. | MEASURED | C1 URL |
| F-2 | Search surfaced other 2026 DRHPs/RHPs, on SEBI (`sebi.gov.in/sebi_data/attachdocs/jul-2026/1783586970465.pdf`), Morgan Stanley's India offer-documents path, and issuer sites. They were not downloaded: SEBI robots was unreachable, and one DRHP sufficed. | UNVERIFIED (snippets only) | — |
| F-3 | Other documents a diligence lawyer typically reviews in bulk were **not sampled**: shareholders'/investment agreements, loan and security documents, charge filings, statutory registers, board/committee minutes, material contracts, title documents, and litigation papers. INFERRED: most of these are private (not public listed-company disclosures), so CLAUDE.md's permitted-sources rule puts them out of reach for sampling. Their size profile is **OPEN**. | INFERRED / OPEN | — |
| F-4 | The Birla Cable Reg 30 intimation (A4) shows that a listed company's *first* public scheme disclosure can be a short cover letter with no scheme or annexures attached. INFERRED: the full bundle appears later, in exchange applications and NCLT meeting notices. | MEASURED (A4) / INFERRED (sequence) | A4 URL |

### E-G. What is held in `corpus/testdocs/` (MEASURED-local)

Local paths are relative to `/Users/nishantsingh/PlacedOn/placedon-law-backend/corpus/testdocs/`. Source URLs per file are in `MANIFEST.md`.

**Raw PDFs (`_raw/`)**

| File | Bytes | PDF pages | Textless pages | Pages with images | Text layer |
|---|---|---|---|---|---|
| icsi_gn_board.pdf | 1,037,285 | 169 | 2 | 2 | yes |
| icsi_gn_general.pdf | 968,434 | 179 | 1 | 1 | yes |
| rm_bm_20240529.pdf | 334,889 | 1 | 0 | 1 | yes |
| rm_bm_20250128.pdf | 7,435,384 | 14 | 0 | 14 | yes (7.4 MB for 14 pp; images on every page) |
| rm_bm_20251103.pdf | 4,166,246 | 18 | 0 | 6 | yes |
| rm_bm_20260507.pdf | 3,894,834 | 22 | 0 | 8 | yes |
| route_agm_2024.pdf | 539,129 | 22 | 0 | 2 | yes |
| route_agm_2025.pdf | 179,266 | 16 | 0 | 1 | yes |
| route_agm_2026.pdf | 243,128 | 16 | 0 | 1 | yes |
| sonata_agm_notice_29th_2024.pdf | 248,090 | 18 | 0 | 1 | yes |
| sonata_outcome_agm_2025.pdf | 5,113,018 | 4 | 0 | 4 | yes |
| sonata_outcome_agm_2026.pdf | 881,907 | 4 | 0 | 4 | yes |
| titan_agm_2025.pdf | 204,071 | 16 | 0 | 1 | yes |
| titan_agm_2026.pdf | 211,426 | 15 | 0 | 1 | yes |

`_raw/` also holds scripts: `dump.py` (332 B), `extract.py` (1,353 B), `slice.py` (633 B). The garbled-text heuristic flagged **0 pages** across all 14 local PDFs.

**Extracted text files** (bytes)

- **agm_notices/**
  - routemobile_20th_agm_notice_2024.txt: 81,705
  - routemobile_21st_agm_notice_2025.txt: 61,681
  - routemobile_22nd_agm_notice_2026.txt: 61,868
  - sonata_29th_agm_notice_2024.txt: 59,412
  - tataelxsi_37th_agm_notice_2026.txt: 68,395
  - tcpl_62nd_agm_notice_2025.txt: 65,338
  - tcpl_63rd_agm_notice_2026.txt: 70,775
  - titan_41st_agm_notice_2025.txt: 59,141
  - titan_42nd_agm_notice_2026.txt: 55,215
- **board_outcomes/**
  - routemobile_outcome_board_meeting_2024-05-29.txt: 3,463
  - routemobile_outcome_board_meeting_2025-01-28.txt: 43,309
  - routemobile_outcome_board_meeting_2025-11-03.txt: 65,219
  - routemobile_outcome_board_meeting_2026-05-07.txt: 83,879
  - sonata_outcome_of_agm_2025.txt: 8,918
  - sonata_outcome_of_agm_2026.txt: 8,113
  - tataelxsi_board_report_ss_statement_2025_26.txt: 817
  - tcpl_board_report_ss_statement_2024_25.txt: 649
  - tcpl_board_report_ss_statement_2025_26.txt: 590
- **icsi_specimens/**
  - 01_board_meeting_notice_annexII.txt: 2,692
  - 02_resolution_by_circulation_annexVI.txt: 1,416
  - 03_minutes_first_board_meeting_annexVII.txt: 17,079
  - 04_minutes_subsequent_board_meeting_annexVIII.txt: 9,132
  - 05_attendance_slip_annexI.txt: 1,378
  - 06_agm_notice_annexII.txt: 16,566
  - 07_egm_notice_annexIII.txt: 9,730
  - 08_board_resolution_convening_egm_annexIX.txt: 1,403
  - 09_minutes_agm_annexXVI.txt: 12,577
  - 10_minutes_egm_annexXVII.txt: 4,480
  - 11_minutes_adjourned_agm_annexXVIII.txt: 3,687
- **minutes_extracts/**
  - README.txt: 778
- **top level**
  - MANIFEST.md: 19,522

Two files in the listing are *extracts* from larger annual reports, not standalone files:
- `tcpl_62nd_agm_notice_2025.txt` covers IAR pp.447–463 (the same B1 file measured above).
- `tataelxsi_37th_agm_notice_2026.txt` covers IAR pp.39–98.

Both page ranges are SOURCED from MANIFEST.md. The parent annual reports are not held.

## Evidence quality

- **Small, non-random sample.** Six external documents: one full scheme bundle, two NCLT orders, one Reg 30 intimation, one annual report, one DRHP. Every figure is an observation about *these files*, not a distribution. No claim is made about typical or median size.
- **The only full scheme bundle is from 2022** (A1). No 2025–26 NCLT meeting-notice bundle was measured. The BSE-hosted candidates found (e.g. `bseindia.com/xml-data/corpfiling/AttachLive/3f4916bf-…pdf`, 17 Jun 2026) were skipped because BSE robots was not determinable.
- **All measurement is automated heuristics without OCR.** The textless test cannot tell a scanned page from a blank one (every range start was checked to have an image, but not every page). The garble detector both over-flags (TCPL) and under-flags (A1 pp.445, 493, 505). `find_tables` undercounts.
- **The large-company skew is real.** TCPL and IBREL are large caps; C1 is a small issuer. Mid-size and unlisted-company documents are unmeasured.
- **Only company-hosted and exchange-hosted copies were measured.** INFERRED: a file uploaded by a user (a lawyer's own scan, a re-printed PDF, a data-room export) could have worse text-layer quality than these.

## Result

1. **Scale.** The largest sampled document types are the scheme meeting-notice bundle, the integrated annual report and the DRHP. Measured sizes: **466–512 PDF pages and 6.7–39.4 MB** (A1, B1, C1, all MEASURED). The longest single file is 512 pages; the heaviest is 39.4 MB.
2. **A scheme "document" is a bundle of about 14 heterogeneous documents** (E-B). The bundle is at least 52% financial statements and results, 19% valuation and fairness, and 12% the scheme itself. It also contains exchange letters, a CCI order, s.232(2)(c) board reports and a complaints report.
3. **Text layer is per-page, not per-file** (A1, MEASURED).
   - A single bundle mixes born-digital pages, whole scanned annexures and corrupted text layers.
   - The scanned parts: 20.7% of pages, at ≈85–95 dpi for most blocks, including all of the unaudited results and half the valuation report.
   - The corrupted layers include a units-of-measure header ("all amounts in ₹ thousands") encoded as nonsense.
4. **NCLT orders are small and clean**: 13–40 pages, 100% text (A2, A3). About half of one order is a regulator-observations table.
5. **Ind AS statements are dense and tabular.**
   - Numeric-token share is ≈5× the narrative sections (13.5–14.5% vs 2.8%).
   - Detection finds at least 2–3 tables per FS page.
   - Standalone and consolidated statements take about a third of a 466-page annual report.
6. **Page-number identity is unstable.** B1 prints two-up spreads as single PDF pages (130 of 466). Neither B1 nor C1 has a usable outline. A1's printed page numbers do match its PDF indices.
7. **The held test corpus is far smaller than the documents above.**
   - Every real listed-company PDF in `corpus/testdocs/_raw/` is **1–22 pages**. The ICSI guidance notes are 169/179.
   - All have text layers and none is garbled.
   - INFERRED: the corpus exercises none of the failure modes measured in A1 (scanned annexures, low-dpi scans, corrupted text layers, bundles of mixed document types) and none of the scale of A1/B1/C1.

## Unresolved issues

- **OPEN.** Size and quality distribution across many schemes: only one bundle measured, and it is from 2022. Recent (2025–26) NCLT meeting notices and SEBI-scheme applications are unmeasured.
- **OPEN.** Whether BSE `AttachLive` and SEBI `attachdocs` may be fetched. Neither host returned a readable robots.txt on 2026-09-14. `checker/robots.py`'s behaviour on "no robots file" vs "unreachable robots" was not checked against these hosts.
- **OPEN.** The exact count of corrupted-text-layer pages in A1 (≥17). No OCR comparison was run, so extracted vs rendered text agreement was not measured on any page.
- **OPEN.** B1's printed-page to PDF-page mapping, and its exact note count.
- **OPEN.** The size profile of private diligence documents (agreements, minutes, registers). They are out of the permitted-source perimeter for sampling.
- **UNVERIFIED.** The A2 order date and parties; the A3 order date (file name only).
- **Not done.** Stable-URL hashing of the sampled files. The files sit in the session scratchpad and are not in the repo.

## Recommended next action

1. **Add one mixed-quality fixture before building intake.** Use a scheme bundle comparable to A1: whole scanned annexures, a garbled text layer, a 500-page bundle. Record URL, SHA-256 and the per-page layer map in `MANIFEST.md`, following the existing acquisition policy. This is the smallest thing that would let PLAN_12's page classifier be tested against a real failure.
2. **Measure 3–5 recent (2025–26) scheme bundles** from hosts with determinable robots (issuer sites, `nsearchives`). The goal is to replace the single-2022-sample caveat with a small range.
3. **Run OCR on A1's textless and garbled pages** and compare against rendered images. That puts a number on what "text layer present" is worth.
4. **Resolve the BSE/SEBI robots question** with `checker/robots.py` itself, not by hand, before either host is used.

## What this means for PLAN_12 (document intake architecture)

All points below are INFERRED design implications of the measurements above.

- **Size envelope.** Intake must accept at least ~40 MB and ~600 PDF pages per file with headroom. B1 alone is 39.4 MB / 466 pages. A1 is 512 pages. A reviewer in a scheme matter plausibly uploads the bundle plus annual reports of each party together, so batch size is multiples of that.
- **Per-page split and per-page routing are required, not optional.**
  - Text/scan routing cannot be decided per file: A1 is 79% text and 21% scanned, interleaved.
  - PLAN_11's "text-layer pages skip OCR" rule needs a third branch. **Text layer present but untrustworthy** (A1 C-1 to C-3) must go to OCR or be flagged, never passed through as text.
  - Needed: a per-page quality gate (stopword/glyph checks at minimum, ideally text-vs-OCR agreement).
- **Units and headers are the highest-risk corruption.** C-1 corrupted the "₹ thousands" units line while the numbers survived. A units error silently scales every figure by 1,000. Per CLAUDE.md's "never repair a defective source", the intake should **flag and preserve** such a page, never auto-decode it. Figures from a page whose units line failed the quality gate should be marked UNVERIFIED.
- **Low-dpi scans.** Most scanned blocks measured ≈85–95 dpi, and one page carries a landscape image on a portrait page. The OCR tier must handle sub-100-dpi input and rotation, and report per-page OCR confidence rather than per-document.
- **Segment the file into documents before classifying.** A1 is 14 document types in one PDF; type classification per file would be wrong. CLAUDE.md's rule that minutes checks must not fire on notices generalises: **Companies Act checks must not fire on a CCI order or a BDO valuation report that happens to sit inside a scheme bundle.** Intake should emit segments (type, page range, confidence), with "unknown segment type" treated as classification uncertainty. An index page like A1 pp.1–2 is a useful but untrusted segmentation hint.
- **Scope.** Roughly half of A1 is financial statements, and much of the rest (valuation, fairness, exchange letters, abridged prospectus) is outside the Companies Act. Intake must pass every segment through `checker/scope.py`. Segments governed by bodies of law that are DECLARED but not held need an explicit refusal, not silence. Which bodies those are was not checked here.
- **Citation identity.** Anchor every citation to (file SHA-256, PDF page index) and store the printed page label separately when detectable. B1's 130 two-up spreads mean "page 45" is ambiguous. Outlines were missing or useless in B1 and C1, so they cannot be relied on for section anchors.
- **Tables are first-class.** FS pages carry ≈2–3+ tables each, ≈14% numeric tokens. Half of A3, an NCLT order, is a table. Extraction that flattens tables to prose will lose the row/column binding that a "missing required information" check depends on.
- **Idempotence and cost.** Per-page hashing lets a re-uploaded bundle, or the same annual report inside two bundles, skip reprocessing. At the measured sizes, a 512-page bundle with 106 OCR pages and 156 FS pages of table extraction is the unit PLAN_12's cost model should be sized against. That is a design input, not a cost measurement.
- **Test corpus gap.** No held fixture exceeds 22 real pages or contains a scanned, garbled or multi-type page. Until one does, PLAN_12's intake claims about mixed documents are untestable in this repo.
