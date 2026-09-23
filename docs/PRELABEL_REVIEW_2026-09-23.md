# Pre-label review list — 2026-09-23

> **This is not an accuracy claim, and it is not ground truth.**
> Agreement between two models is NOT evidence that either is correct. Both can be wrong in the same way, and in this repository they already have been — Indian digit grouping has produced the same 10x misreading more than once. Nothing here is an accuracy measurement. Expert review by a practising Company Secretary (research/TASKS.md H-001) is still required.

Two models read each public corpus document independently, with the same prompt and the same declared fields. Every value below survived this repository's own gates: the span must be present in the document, the span must yield the value, and the span must not name a different field. A value that failed a gate was **dropped, never repaired** — the drop is recorded, not corrected.

Where both models produced the same supported value, the field is labelled **model-verified, NOT expert-verified**. Where they differ, or only one of them supports a value, there is a row below for a person to settle.

## What ran

| | |
|---|---|
| Model A | `azure:llama-3-3-70b`, temperature 0 |
| Model B | `azure:gpt-5-mini`, temperature None |
| Corpus | `corpus/testdocs/` — 29 public documents (18 real filings, 11 ICSI specimens) |
| Documents compared | 26 |
| Fields per document | 10 |
| Agreements | 16 — model-verified, NOT expert-verified |
| Disagreements (both supported, different values) | 1 |
| One-sided (only one model supported a value) | 11 |
| Neither model supported a value | 232 |

Anchors are `file:line` in the corpus text file, reproducible with `sed -n '<line>p' <file>`. **No page numbers**: the repository's own page reader agrees with an independent reader on 0 of 14 corpus PDFs (`docs/OVERNIGHT_REPORT_2026_09_14.md` §4), so a page number here would look checkable and not be.

## Documents not compared

A one-sided row says one model supported a value and the other did not. That is false when the other model never answered, so these documents produce no rows at all.

| Document | Why |
|---|---|
| `agm_notices/routemobile_20th_agm_notice_2024` | azure:llama-3-3-70b returned no answer — ModelUnavailable: Azure HTTP 429: {"error":{"code":"RateLimitReached","message":"Your requests to Llama-3.3-70B-Instruct for llama-3-3-70b in uaenort… |
| `board_outcomes/routemobile_outcome_board_meeting_2025-01-28` | azure:gpt-5-mini returned no answer — ModelUnavailable: the Azure reply did not finish (finish_reason='length'); a truncated reply is not an answer |
| `board_outcomes/routemobile_outcome_board_meeting_2026-05-07` | azure:llama-3-3-70b returned no answer — ModelUnavailable: Azure HTTP 429: {"error":{"code":"RateLimitReached","message":"Your requests to Llama-3.3-70B-Instruct for llama-3-3-70b in uaenort… |

## The list

Sorted by how likely the field is to change an obligation row: the s.135 CSR and s.2(85) small-company inputs first, then the date and period fields that decide which year and which deadline those figures are tested against, then identity. At equal priority a contradiction sorts before a gap. **12 rows kept**, a budget of 60.

Verdict column is blank by design. No agent writes it.

| # | Document | Anchor | Field | A · llama-3-3-70b | B · gpt-5-mini | What the document says there | Verdict |
|---:|---|---|---|---|---|---|---|
| 1 | `icsi_specimens/07_egm_notice_annexIII` | `corpus/testdocs/icsi_specimens/07_egm_notice_annexI…` | `company_class` | `public`<br>read from “every listed public company” | `listed public company`<br>**not a value `CompanyClass` accepts**<br>read from “listed public company” | ble provisions of the Companies Act, 1956. He joined the Board in May 2010. Section 149 of the Companies Act, 2013, provides that every listed public company shall have at least one third of the total number of Directors as Independent Dir… |  |
| 2 | `agm_notices/routemobile_21st_agm_notice_2025` | `corpus/testdocs/agm_notices/routemobile_21st_agm_no…` | `company_class` | — proposed `Public`, dropped by `FACT_VALUE_UNSUPPORTED`<br>*(this IS a value `CompanyClass` accepts)*<br>gate said: the span is present but does not support the value ('Public' does not appear in the quoted span)<br>from “L72900MH2004PLC146323” | `Limited`<br>**not a value `CompanyClass` accepts**<br>read from “Route Mobile Limited (“Company”)” | NOTICE NOTICE is hereby given that the Twenty First (“21st”) Annual General Meeting (“AGM”) of the members of Route Mobile Limited (“Company”) will be held on Friday, September 12, 2025 at 3:30 p.m. (IST) through Video Conferencing (“VC”)/… |  |
| 3 | `agm_notices/tcpl_62nd_agm_notice_2025` | `corpus/testdocs/agm_notices/tcpl_62nd_agm_notice_20…` | `company_class` | — proposed `Public`, dropped by `FACT_VALUE_UNSUPPORTED`<br>*(this IS a value `CompanyClass` accepts)*<br>gate said: the span is present but does not support the value ('Public' does not appear in the quoted span)<br>from “L15491WB1962PLC031425” | `Tata Consumer Products Limited`<br>**not a value `CompanyClass` accepts**<br>read from “Tata Consumer Products Limited” | Notice of Annual General Meeting Notice is hereby given that the 62nd Annual General Meeting of Tata Consumer Products Limited will be held on Wednesday, June 18, 2025, at 10:30 a.m. (IST) through Video Conferencing / Other Audio-Visual Me… |  |
| 4 | `agm_notices/titan_41st_agm_notice_2025` | `corpus/testdocs/agm_notices/titan_41st_agm_notice_2…` | `company_class` | — proposed `Public`, dropped by `FACT_VALUE_UNSUPPORTED`<br>*(this IS a value `CompanyClass` accepts)*<br>gate said: the span is present but does not support the value ('Public' does not appear in the quoted span)<br>from “L74999TZ1984PLC001456” | `COMPANY LIMITED`<br>**not a value `CompanyClass` accepts**<br>read from “TITAN COMPANY LIMITED” | 1 TITAN COMPANY LIMITED Notice Notice Notice is hereby given pursuant to Sections 96 and 101 of the Companies Act, 2013 that the Forty-First Annual Gene |  |
| 5 | `board_outcomes/sonata_outcome_of_agm_2025` | `corpus/testdocs/board_outcomes/sonata_outcome_of_ag…` | `company_class` | — proposed `Public`, dropped by `FACT_VALUE_UNSUPPORTED`<br>*(this IS a value `CompanyClass` accepts)*<br>gate said: the span is present but does not support the value ('Public' does not appear in the quoted span)<br>from “Sonata Software Limited - SSL” | `Limited`<br>**not a value `CompanyClass` accepts**<br>read from “Sonata Software Limited - SSL” | Sonata Software Limited - SSL Registered Office: 208, T V Industrial Estate, 2nd Floor, S K Ahire Marg, Worli, Mumbai – 400 030 Corporate Office: Tower-A, So |  |
| 6 | `icsi_specimens/04_minutes_subsequent_board_…` | `corpus/testdocs/icsi_specimens/04_minutes_subsequen…` | `paid_up_capital_rupees` | `1000000`<br>read from “10,00,000 equity shares” | — (said nothing) | ng Rs. 10,00,000, be paid on the ..................... (date), out of the profits of the company for the year ending ........, on 10,00,000 equity shares, to those equity shareholders whose names appear in the Register of Members of the co… |  |
| 7 | `agm_notices/sonata_29th_agm_notice_2024` | `corpus/testdocs/agm_notices/sonata_29th_agm_notice_…` | `financial_year` | `2023-24`<br>read from “Annual Report 2023-24” | — proposed `2024-03-31`, dropped by `FACT_VALUE_UNSUPPORTED`<br>gate said: the span is present but does not support the value ('2024-03-31' does not appear in the quoted span)<br>from “Adoption of Financial Statements for the Financial Year ended March 31, 2024.” | Annual Report 2023-24 1 SONATA SOFTWARE LIMITED (CIN: L72200MH1994PLC082110) Registered Office: 208, T V Industrial Estate, 2nd floor, S. K. Ahire Marg |  |
| 8 | `agm_notices/tcpl_62nd_agm_notice_2025` | `corpus/testdocs/agm_notices/tcpl_62nd_agm_notice_20…` | `financial_year` | `2025`<br>read from “for the financial year ended March 31, 2025” | — proposed `2025-03-31`, dropped by `FACT_VALUE_UNSUPPORTED`<br>gate said: the span is present but does not support the value ('2025-03-31' does not appear in the quoted span)<br>from “financial year ended March 31, 2025” | UDITED STANDALONE FINANCIAL STATEMENTS To receive, consider and adopt the Audited Standalone Financial Statements of the Company for the financial year ended March 31, 2025, together with the Reports of the Board of Directors and Auditors … |  |
| 9 | `agm_notices/tcpl_63rd_agm_notice_2026` | `corpus/testdocs/agm_notices/tcpl_63rd_agm_notice_20…` | `financial_year` | `2025-26`<br>read from “Integrated Annual Report 2025-26” | — proposed `2026-03-31`, dropped by `FACT_VALUE_UNSUPPORTED`<br>gate said: the span is present but does not support the value ('2026-03-31' does not appear in the quoted span)<br>from “for the financial year ended March 31, 2026,” | necessary, proper or expedient, to give effect to this resolution and for matters connected therewith or incidental thereto.” 490 Integrated Annual Report 2025-26 Notes: 1. The Ministry of Corporate Affairs (‘MCA’) allows companies to hold… |  |
| 10 | `agm_notices/titan_42nd_agm_notice_2026` | `corpus/testdocs/agm_notices/titan_42nd_agm_notice_2…` | `financial_year` | `2025-26`<br>read from “Annual Report 2025-26” | — proposed `2026-03-31`, dropped by `FACT_VALUE_UNSUPPORTED`<br>gate said: the span is present but does not support the value ('2026-03-31' does not appear in the quoted span)<br>from “31st March 2026” | Financial Statements Statutory Reports Corporate Overview 1 Annual Report 2025-26 Titan Company Limited Notice is hereby given pursuant to Sections 96 and 101 of the Companies Act, 2013 (the Act) that the Forty |  |
| 11 | `board_outcomes/routemobile_outcome_board_me…` | `corpus/testdocs/board_outcomes/routemobile_outcome_…` | `financial_year` | — proposed `2025-2026`, dropped by `FACT_VALUE_UNSUPPORTED`<br>gate said: the span is present but does not support the value ('2025-2026' does not appear in the quoted span)<br>from “Ref No: RML/2025-26/626” | `F.Y. 2025-26`<br>read from “for the F.Y. 2025-26:” | t www.routemobile.com. 2. Declaration of Second Interim Dividend of Rs. 3/- per equity share of Rs. 10/- each of the Company for the F.Y. 2025-26: Series Equity (EQ) Record Date November 10, 2025 (Pursuant to Regulation 42 of the Listing R… |  |
| 12 | `board_outcomes/sonata_outcome_of_agm_2025` | `corpus/testdocs/board_outcomes/sonata_outcome_of_ag…` | `financial_year` | `2025`<br>read from “Financial Year ended 31st March, 2025” | — proposed `2025-03-31`, dropped by `FACT_VALUE_UNSUPPORTED`<br>gate said: the span is present but does not support the value ('2025-03-31' does not appear in the quoted span)<br>from “Adoption of Financial Statements for the Financial Year ended 31st March, 2025;” | th AGM dated 7th May, 2025, were transacted at the Meeting: Ordinary Business: 1. Adoption of Financial Statements for the Financial Year ended 31st March, 2025; 2. Declaration of Final Dividend of ₹ 4.40 per equity share (i.e. 440%) for t… |  |

## The same shape, repeated

Grouped by field and outcome, counted mechanically, with the distinct values each model produced shown verbatim. Nothing here is characterised — read the values. A row that recurs across many documents is one thing to settle, not many.

| Field | Outcome | Rows | A · llama-3-3-70b produced | B · gpt-5-mini produced | Already open as |
|---|---|---:|---|---|---|
| `financial_year` | ONE_SIDED | 6 | 2023-24; 2025; 2025-26; (dropped by FACT_VALUE_UNSUPPORTED) 2025-2026 | (dropped by FACT_VALUE_UNSUPPORTED) 2024-03-31; (dropped by FACT_VALUE_UNSUPPORTED) 2025-03-31; (dropped by FACT_VALUE_UNSUPPORTED) 2026-03-31; F.Y. 2025-26 | — |
| `company_class` | ONE_SIDED | 4 | (dropped by FACT_VALUE_UNSUPPORTED) Public [a CompanyClass value] | Limited [NOT a CompanyClass value]; Tata Consumer Products Limited [NOT a CompanyClass value]; COMPANY LIMITED [NOT a CompanyClass value] | research/TASKS.md L-007 — map document wording to CompanyClass, or keep the extracted class display-only. Open since 14-09-2026, founder-owned, blocked on an interpretiv… |
| `company_class` | DISAGREE | 1 | public [a CompanyClass value] | listed public company [NOT a CompanyClass value] | research/TASKS.md L-007 — map document wording to CompanyClass, or keep the extracted class display-only. Open since 14-09-2026, founder-owned, blocked on an interpretiv… |
| `paid_up_capital_rupees` | ONE_SIDED | 1 | 1000000 | (said nothing) | — |

## Agreements — model-verified, NOT expert-verified

Listed so the founder can see what the two models did not disagree about. **Agreement is not correctness.** These are not verified, and none of them may be cited as accurate.

**"The document against itself"** is not a model output. It is this repository scanning the document for another declaration of the same field and reporting what it found, using the same grammar the extractor validates against. A value there means the two models agreed on one of the things the document says, while the document says another — so the agreement measured that both read the same declaration, not that the document declares one thing. It is checked only for `cin`, because only a field with a strict grammar makes another occurrence *another declaration of the same thing*; a date or a rupee figure repeating in a notice is ordinary. The rule is `checker/document_date.py`'s, generalised: every declaration the reader can read must agree, or the document does not declare one. Nothing is repaired and nothing is chosen — see `docs/SOURCE_DEFECTS.md` SD-006 for the filing that made this necessary.

| Document | Field | Value | The document against itself | Anchor |
|---|---|---|---|---|
| `agm_notices/titan_41st_agm_notice_2025` | `document_date` | `2025-05-08` | — | `corpus/testdocs/agm_notices/titan_41st_agm_notice_2…` |
| `agm_notices/titan_42nd_agm_notice_2026` | `document_date` | `2026-06-29` | — | `corpus/testdocs/agm_notices/titan_42nd_agm_notice_2…` |
| `board_outcomes/sonata_outcome_of_agm_2025` | `document_date` | `2025-07-31` | — | `corpus/testdocs/board_outcomes/sonata_outcome_of_ag…` |
| `board_outcomes/sonata_outcome_of_agm_2026` | `document_date` | `2026-07-31` | — | `corpus/testdocs/board_outcomes/sonata_outcome_of_ag…` |
| `agm_notices/routemobile_21st_agm_notice_2025` | `cin` | `L72900MH2004PLC146323` | — | `corpus/testdocs/agm_notices/routemobile_21st_agm_no…` |
| `agm_notices/routemobile_22nd_agm_notice_2026` | `cin` | `L72900MH2004PLC146323` | — | `corpus/testdocs/agm_notices/routemobile_22nd_agm_no…` |
| `agm_notices/sonata_29th_agm_notice_2024` | `cin` | `L72200MH1994PLC082110` | — | `corpus/testdocs/agm_notices/sonata_29th_agm_notice_…` |
| `agm_notices/tataelxsi_37th_agm_notice_2026` | `cin` | `L85110KA1989PLC009968` | — | `corpus/testdocs/agm_notices/tataelxsi_37th_agm_noti…` |
| `agm_notices/tcpl_62nd_agm_notice_2025` | `cin` | `L15491WB1962PLC031425` | — | `corpus/testdocs/agm_notices/tcpl_62nd_agm_notice_20…` |
| `agm_notices/tcpl_63rd_agm_notice_2026` | `cin` | `L15491WB1962PLC031425` | — | `corpus/testdocs/agm_notices/tcpl_63rd_agm_notice_20…` |
| `agm_notices/titan_41st_agm_notice_2025` | `cin` | `L74999TZ1984PLC001456` | — | `corpus/testdocs/agm_notices/titan_41st_agm_notice_2…` |
| `agm_notices/titan_42nd_agm_notice_2026` | `cin` | `L74999TZ1984PLC001456` | — | `corpus/testdocs/agm_notices/titan_42nd_agm_notice_2…` |
| `board_outcomes/routemobile_outcome_board_me…` | `cin` | `L72900MH2004PLC146323` | — | `corpus/testdocs/board_outcomes/routemobile_outcome_…` |
| `board_outcomes/routemobile_outcome_board_me…` | `cin` | `L72900MH2004PLC746323` | `L72900MH2004PLC146323` | `corpus/testdocs/board_outcomes/routemobile_outcome_…` |
| `board_outcomes/sonata_outcome_of_agm_2025` | `cin` | `L72200MH1994PLC082110` | — | `corpus/testdocs/board_outcomes/sonata_outcome_of_ag…` |
| `board_outcomes/sonata_outcome_of_agm_2026` | `cin` | `L72200MH1994PLC082110` | — | `corpus/testdocs/board_outcomes/sonata_outcome_of_ag…` |

## Cost

| Model | Calls | Tokens in | Tokens out | ₹ |
|---|---:|---:|---:|---|
| `azure:llama-3-3-70b` | 0 | 0 | 0 | unpriced — see below |
| `azure:gpt-5-mini` | 3 | 20893 | 5366 | unpriced — see below |

**₹ priced by `backend/budget.cost_inr`: ₹0.0 against the ₹500.0 job cap.** These deployments are not in backend/budget.PRICING, so no rupee figure is computed for them. They are served on the Azure for Students credit. Tokens are reported; the rupee cost is OPEN, not zero. A ceiling of 90 requests bounds the credit spend that the rupee cap cannot see; 10 requests were made.

Rate-limited retries (HTTP 429, the deployment's throughput — not a model that could not read the document): `azure:llama-3-3-70b` ×4.

## What the gates dropped

Recorded, not repaired. A model proposed these and the repository refused them; they are evidence about the models, not about the documents.

| Document | Model | Field | Gate |
|---|---|---|---|
| `agm_notices/routemobile_20th_agm_notice_2024` | `azure:gpt-5-mini` | `document_date` | `FACT_VALUE_UNSUPPORTED` |
| `agm_notices/routemobile_20th_agm_notice_2024` | `azure:gpt-5-mini` | `financial_year` | `FACT_VALUE_UNSUPPORTED` |
| `agm_notices/routemobile_20th_agm_notice_2024` | `azure:gpt-5-mini` | `turnover_rupees` | `FACT_VALUE_UNSUPPORTED` |
| `agm_notices/routemobile_20th_agm_notice_2024` | `azure:gpt-5-mini` | `cin` | `FACT_VALUE_UNSUPPORTED` |
| `agm_notices/routemobile_21st_agm_notice_2025` | `azure:llama-3-3-70b` | `document_date` | `FACT_VALUE_UNSUPPORTED` |
| `agm_notices/routemobile_21st_agm_notice_2025` | `azure:llama-3-3-70b` | `incorporation_date` | `FACT_VALUE_UNSUPPORTED` |
| `agm_notices/routemobile_21st_agm_notice_2025` | `azure:llama-3-3-70b` | `company_class` | `FACT_VALUE_UNSUPPORTED` |
| `agm_notices/routemobile_21st_agm_notice_2025` | `azure:llama-3-3-70b` | `financial_year` | `FACT_NOT_GROUNDED` |
| `agm_notices/routemobile_21st_agm_notice_2025` | `azure:gpt-5-mini` | `document_date` | `FACT_VALUE_UNSUPPORTED` |
| `agm_notices/routemobile_21st_agm_notice_2025` | `azure:gpt-5-mini` | `financial_year` | `FACT_VALUE_UNSUPPORTED` |
| `agm_notices/routemobile_22nd_agm_notice_2026` | `azure:llama-3-3-70b` | `document_date` | `FACT_VALUE_UNSUPPORTED` |
| `agm_notices/routemobile_22nd_agm_notice_2026` | `azure:llama-3-3-70b` | `incorporation_date` | `FACT_VALUE_UNSUPPORTED` |
| `agm_notices/routemobile_22nd_agm_notice_2026` | `azure:llama-3-3-70b` | `company_class` | `FACT_VALUE_UNSUPPORTED` |
| `agm_notices/routemobile_22nd_agm_notice_2026` | `azure:llama-3-3-70b` | `financial_year` | `FACT_NOT_GROUNDED` |
| `agm_notices/routemobile_22nd_agm_notice_2026` | `azure:gpt-5-mini` | `document_date` | `FACT_VALUE_UNSUPPORTED` |
| `agm_notices/routemobile_22nd_agm_notice_2026` | `azure:gpt-5-mini` | `financial_year` | `FACT_VALUE_UNSUPPORTED` |
| `agm_notices/sonata_29th_agm_notice_2024` | `azure:llama-3-3-70b` | `document_date` | `FACT_NOT_GROUNDED` |
| `agm_notices/sonata_29th_agm_notice_2024` | `azure:llama-3-3-70b` | `incorporation_date` | `FACT_VALUE_UNSUPPORTED` |
| `agm_notices/sonata_29th_agm_notice_2024` | `azure:llama-3-3-70b` | `company_class` | `FACT_VALUE_UNSUPPORTED` |
| `agm_notices/sonata_29th_agm_notice_2024` | `azure:gpt-5-mini` | `document_date` | `FACT_VALUE_UNSUPPORTED` |
| `agm_notices/sonata_29th_agm_notice_2024` | `azure:gpt-5-mini` | `financial_year` | `FACT_VALUE_UNSUPPORTED` |
| `agm_notices/tataelxsi_37th_agm_notice_2026` | `azure:llama-3-3-70b` | `document_date` | `FACT_VALUE_UNSUPPORTED` |
| `agm_notices/tataelxsi_37th_agm_notice_2026` | `azure:llama-3-3-70b` | `incorporation_date` | `FACT_VALUE_UNSUPPORTED` |
| `agm_notices/tataelxsi_37th_agm_notice_2026` | `azure:llama-3-3-70b` | `company_class` | `FACT_VALUE_UNSUPPORTED` |
| `agm_notices/tataelxsi_37th_agm_notice_2026` | `azure:llama-3-3-70b` | `financial_year` | `FACT_VALUE_UNSUPPORTED` |
| `agm_notices/tataelxsi_37th_agm_notice_2026` | `azure:llama-3-3-70b` | `paid_up_capital_rupees` | `FACT_NOT_GROUNDED` |
| `agm_notices/tataelxsi_37th_agm_notice_2026` | `azure:llama-3-3-70b` | `turnover_rupees` | `FACT_NOT_GROUNDED` |
| `agm_notices/tataelxsi_37th_agm_notice_2026` | `azure:llama-3-3-70b` | `net_worth_rupees` | `FACT_NOT_GROUNDED` |
| `agm_notices/tataelxsi_37th_agm_notice_2026` | `azure:llama-3-3-70b` | `net_profit_rupees` | `FACT_NOT_GROUNDED` |
| `agm_notices/tataelxsi_37th_agm_notice_2026` | `azure:llama-3-3-70b` | `director_count` | `FACT_NOT_GROUNDED` |
| `agm_notices/tataelxsi_37th_agm_notice_2026` | `azure:gpt-5-mini` | `document_date` | `FACT_VALUE_UNSUPPORTED` |
| `agm_notices/tataelxsi_37th_agm_notice_2026` | `azure:gpt-5-mini` | `financial_year` | `FACT_NOT_GROUNDED` |
| `agm_notices/tataelxsi_37th_agm_notice_2026` | `azure:gpt-5-mini` | `turnover_rupees` | `FACT_VALUE_UNSUPPORTED` |
| `agm_notices/tataelxsi_37th_agm_notice_2026` | `azure:gpt-5-mini` | `net_worth_rupees` | `FACT_VALUE_UNSUPPORTED` |
| `agm_notices/tataelxsi_37th_agm_notice_2026` | `azure:gpt-5-mini` | `net_profit_rupees` | `FACT_VALUE_UNSUPPORTED` |
| `agm_notices/tcpl_62nd_agm_notice_2025` | `azure:llama-3-3-70b` | `document_date` | `FACT_VALUE_UNSUPPORTED` |
| `agm_notices/tcpl_62nd_agm_notice_2025` | `azure:llama-3-3-70b` | `company_class` | `FACT_VALUE_UNSUPPORTED` |
| `agm_notices/tcpl_62nd_agm_notice_2025` | `azure:llama-3-3-70b` | `incorporation_date` | `FACT_VALUE_UNSUPPORTED` |
| `agm_notices/tcpl_62nd_agm_notice_2025` | `azure:gpt-5-mini` | `document_date` | `FACT_VALUE_UNSUPPORTED` |
| `agm_notices/tcpl_62nd_agm_notice_2025` | `azure:gpt-5-mini` | `financial_year` | `FACT_VALUE_UNSUPPORTED` |
| `agm_notices/tcpl_63rd_agm_notice_2026` | `azure:llama-3-3-70b` | `document_date` | `FACT_VALUE_UNSUPPORTED` |
| `agm_notices/tcpl_63rd_agm_notice_2026` | `azure:llama-3-3-70b` | `company_class` | `FACT_VALUE_UNSUPPORTED` |
| `agm_notices/tcpl_63rd_agm_notice_2026` | `azure:llama-3-3-70b` | `paid_up_capital_rupees` | `FACT_NOT_GROUNDED` |
| `agm_notices/tcpl_63rd_agm_notice_2026` | `azure:llama-3-3-70b` | `turnover_rupees` | `FACT_NOT_GROUNDED` |
| `agm_notices/tcpl_63rd_agm_notice_2026` | `azure:llama-3-3-70b` | `net_worth_rupees` | `FACT_NOT_GROUNDED` |
| `agm_notices/tcpl_63rd_agm_notice_2026` | `azure:llama-3-3-70b` | `net_profit_rupees` | `FACT_NOT_GROUNDED` |
| `agm_notices/tcpl_63rd_agm_notice_2026` | `azure:llama-3-3-70b` | `director_count` | `FACT_NOT_GROUNDED` |
| `agm_notices/tcpl_63rd_agm_notice_2026` | `azure:gpt-5-mini` | `document_date` | `FACT_VALUE_UNSUPPORTED` |
| `agm_notices/tcpl_63rd_agm_notice_2026` | `azure:gpt-5-mini` | `financial_year` | `FACT_VALUE_UNSUPPORTED` |
| `agm_notices/tcpl_63rd_agm_notice_2026` | `azure:gpt-5-mini` | `company_class` | `FACT_MISBOUND` |
| `agm_notices/titan_41st_agm_notice_2025` | `azure:llama-3-3-70b` | `incorporation_date` | `FACT_VALUE_UNSUPPORTED` |
| `agm_notices/titan_41st_agm_notice_2025` | `azure:llama-3-3-70b` | `company_class` | `FACT_VALUE_UNSUPPORTED` |
| `agm_notices/titan_41st_agm_notice_2025` | `azure:llama-3-3-70b` | `financial_year` | `FACT_VALUE_UNSUPPORTED` |
| `agm_notices/titan_41st_agm_notice_2025` | `azure:gpt-5-mini` | `financial_year` | `FACT_VALUE_UNSUPPORTED` |
| `agm_notices/titan_42nd_agm_notice_2026` | `azure:llama-3-3-70b` | `incorporation_date` | `FACT_VALUE_UNSUPPORTED` |
| `agm_notices/titan_42nd_agm_notice_2026` | `azure:llama-3-3-70b` | `company_class` | `FACT_VALUE_UNSUPPORTED` |
| `agm_notices/titan_42nd_agm_notice_2026` | `azure:gpt-5-mini` | `financial_year` | `FACT_VALUE_UNSUPPORTED` |
| `board_outcomes/routemobile_outcome_board_me…` | `azure:llama-3-3-70b` | `document_date` | `FACT_VALUE_UNSUPPORTED` |
| `board_outcomes/routemobile_outcome_board_me…` | `azure:llama-3-3-70b` | `incorporation_date` | `FACT_VALUE_UNSUPPORTED` |
| `board_outcomes/routemobile_outcome_board_me…` | `azure:gpt-5-mini` | `document_date` | `FACT_VALUE_UNSUPPORTED` |
| `board_outcomes/routemobile_outcome_board_me…` | `azure:llama-3-3-70b` | `document_date` | `FACT_VALUE_UNSUPPORTED` |
| `board_outcomes/routemobile_outcome_board_me…` | `azure:llama-3-3-70b` | `incorporation_date` | `FACT_VALUE_UNSUPPORTED` |
| `board_outcomes/routemobile_outcome_board_me…` | `azure:llama-3-3-70b` | `company_class` | `FACT_NOT_GROUNDED` |
| `board_outcomes/routemobile_outcome_board_me…` | `azure:llama-3-3-70b` | `paid_up_capital_rupees` | `FACT_NOT_GROUNDED` |
| `board_outcomes/routemobile_outcome_board_me…` | `azure:llama-3-3-70b` | `turnover_rupees` | `FACT_NOT_GROUNDED` |
| `board_outcomes/routemobile_outcome_board_me…` | `azure:llama-3-3-70b` | `net_worth_rupees` | `FACT_NOT_GROUNDED` |
| `board_outcomes/routemobile_outcome_board_me…` | `azure:llama-3-3-70b` | `net_profit_rupees` | `FACT_NOT_GROUNDED` |
| `board_outcomes/routemobile_outcome_board_me…` | `azure:llama-3-3-70b` | `director_count` | `FACT_NOT_GROUNDED` |
| `board_outcomes/routemobile_outcome_board_me…` | `azure:llama-3-3-70b` | `document_date` | `FACT_VALUE_UNSUPPORTED` |
| `board_outcomes/routemobile_outcome_board_me…` | `azure:llama-3-3-70b` | `incorporation_date` | `FACT_VALUE_UNSUPPORTED` |
| `board_outcomes/routemobile_outcome_board_me…` | `azure:llama-3-3-70b` | `company_class` | `FACT_VALUE_UNSUPPORTED` |
| `board_outcomes/routemobile_outcome_board_me…` | `azure:llama-3-3-70b` | `financial_year` | `FACT_VALUE_UNSUPPORTED` |
| `board_outcomes/routemobile_outcome_board_me…` | `azure:llama-3-3-70b` | `paid_up_capital_rupees` | `FACT_VALUE_UNSUPPORTED` |
| `board_outcomes/routemobile_outcome_board_me…` | `azure:gpt-5-mini` | `document_date` | `FACT_VALUE_UNSUPPORTED` |
| `board_outcomes/routemobile_outcome_board_me…` | `azure:gpt-5-mini` | `paid_up_capital_rupees` | `FACT_VALUE_UNSUPPORTED` |
| `board_outcomes/routemobile_outcome_board_me…` | `azure:gpt-5-mini` | `turnover_rupees` | `FACT_VALUE_UNSUPPORTED` |
| `board_outcomes/routemobile_outcome_board_me…` | `azure:gpt-5-mini` | `net_worth_rupees` | `FACT_VALUE_UNSUPPORTED` |
| `board_outcomes/routemobile_outcome_board_me…` | `azure:gpt-5-mini` | `net_profit_rupees` | `FACT_VALUE_UNSUPPORTED` |
| `board_outcomes/routemobile_outcome_board_me…` | `azure:gpt-5-mini` | `document_date` | `FACT_VALUE_UNSUPPORTED` |
| `board_outcomes/routemobile_outcome_board_me…` | `azure:gpt-5-mini` | `financial_year` | `FACT_VALUE_UNSUPPORTED` |
| `board_outcomes/routemobile_outcome_board_me…` | `azure:gpt-5-mini` | `paid_up_capital_rupees` | `FACT_VALUE_UNSUPPORTED` |
| `board_outcomes/routemobile_outcome_board_me…` | `azure:gpt-5-mini` | `turnover_rupees` | `FACT_VALUE_UNSUPPORTED` |
| `board_outcomes/routemobile_outcome_board_me…` | `azure:gpt-5-mini` | `net_profit_rupees` | `FACT_VALUE_UNSUPPORTED` |
| `board_outcomes/sonata_outcome_of_agm_2025` | `azure:llama-3-3-70b` | `incorporation_date` | `FACT_VALUE_UNSUPPORTED` |
| `board_outcomes/sonata_outcome_of_agm_2025` | `azure:llama-3-3-70b` | `company_class` | `FACT_VALUE_UNSUPPORTED` |
| `board_outcomes/sonata_outcome_of_agm_2025` | `azure:llama-3-3-70b` | `director_count` | `FACT_VALUE_UNSUPPORTED` |
| `board_outcomes/sonata_outcome_of_agm_2025` | `azure:gpt-5-mini` | `financial_year` | `FACT_VALUE_UNSUPPORTED` |
| `board_outcomes/sonata_outcome_of_agm_2026` | `azure:llama-3-3-70b` | `incorporation_date` | `FACT_VALUE_UNSUPPORTED` |
| `board_outcomes/sonata_outcome_of_agm_2026` | `azure:llama-3-3-70b` | `company_class` | `FACT_VALUE_UNSUPPORTED` |
| `board_outcomes/sonata_outcome_of_agm_2026` | `azure:llama-3-3-70b` | `financial_year` | `FACT_VALUE_UNSUPPORTED` |
| `board_outcomes/sonata_outcome_of_agm_2026` | `azure:llama-3-3-70b` | `paid_up_capital_rupees` | `FACT_NOT_GROUNDED` |
| `board_outcomes/sonata_outcome_of_agm_2026` | `azure:llama-3-3-70b` | `turnover_rupees` | `FACT_NOT_GROUNDED` |
| `board_outcomes/sonata_outcome_of_agm_2026` | `azure:llama-3-3-70b` | `net_worth_rupees` | `FACT_NOT_GROUNDED` |
| `board_outcomes/sonata_outcome_of_agm_2026` | `azure:llama-3-3-70b` | `net_profit_rupees` | `FACT_NOT_GROUNDED` |
| `board_outcomes/sonata_outcome_of_agm_2026` | `azure:llama-3-3-70b` | `director_count` | `FACT_NOT_GROUNDED` |
| `board_outcomes/sonata_outcome_of_agm_2026` | `azure:gpt-5-mini` | `financial_year` | `FACT_VALUE_UNSUPPORTED` |
| `icsi_specimens/03_minutes_first_board_meeti…` | `azure:llama-3-3-70b` | `incorporation_date` | `FACT_VALUE_UNSUPPORTED` |
| `icsi_specimens/03_minutes_first_board_meeti…` | `azure:llama-3-3-70b` | `director_count` | `FACT_VALUE_UNSUPPORTED` |
| `icsi_specimens/03_minutes_first_board_meeti…` | `azure:llama-3-3-70b` | `cin` | `FACT_VALUE_UNSUPPORTED` |
| `icsi_specimens/04_minutes_subsequent_board_…` | `azure:llama-3-3-70b` | `turnover_rupees` | `FACT_NOT_GROUNDED` |
| `icsi_specimens/04_minutes_subsequent_board_…` | `azure:llama-3-3-70b` | `net_worth_rupees` | `FACT_NOT_GROUNDED` |
| `icsi_specimens/04_minutes_subsequent_board_…` | `azure:llama-3-3-70b` | `net_profit_rupees` | `FACT_NOT_GROUNDED` |
| `icsi_specimens/04_minutes_subsequent_board_…` | `azure:llama-3-3-70b` | `director_count` | `FACT_VALUE_UNSUPPORTED` |
| `icsi_specimens/04_minutes_subsequent_board_…` | `azure:llama-3-3-70b` | `cin` | `FACT_NOT_GROUNDED` |
| `icsi_specimens/04_minutes_subsequent_board_…` | `azure:llama-3-3-70b` | `document_date` | `FACT_NOT_GROUNDED` |
| `icsi_specimens/04_minutes_subsequent_board_…` | `azure:llama-3-3-70b` | `incorporation_date` | `FACT_NOT_GROUNDED` |
| `icsi_specimens/04_minutes_subsequent_board_…` | `azure:llama-3-3-70b` | `company_class` | `FACT_NOT_GROUNDED` |
| `icsi_specimens/04_minutes_subsequent_board_…` | `azure:llama-3-3-70b` | `financial_year` | `FACT_NOT_GROUNDED` |
| `icsi_specimens/04_minutes_subsequent_board_…` | `azure:gpt-5-mini` | `director_count` | `FACT_VALUE_UNSUPPORTED` |
| `icsi_specimens/06_agm_notice_annexII` | `azure:llama-3-3-70b` | `financial_year` | `FACT_VALUE_UNSUPPORTED` |
| `icsi_specimens/06_agm_notice_annexII` | `azure:llama-3-3-70b` | `cin` | `FACT_VALUE_UNSUPPORTED` |
| `icsi_specimens/07_egm_notice_annexIII` | `azure:llama-3-3-70b` | `cin` | `FACT_VALUE_UNSUPPORTED` |
| `icsi_specimens/07_egm_notice_annexIII` | `azure:llama-3-3-70b` | `director_count` | `FACT_NOT_GROUNDED` |
| `icsi_specimens/07_egm_notice_annexIII` | `azure:llama-3-3-70b` | `document_date` | `FACT_VALUE_UNSUPPORTED` |
| `icsi_specimens/07_egm_notice_annexIII` | `azure:llama-3-3-70b` | `financial_year` | `FACT_NOT_GROUNDED` |
| `icsi_specimens/07_egm_notice_annexIII` | `azure:llama-3-3-70b` | `incorporation_date` | `FACT_NOT_GROUNDED` |
| `icsi_specimens/07_egm_notice_annexIII` | `azure:llama-3-3-70b` | `net_profit_rupees` | `FACT_NOT_GROUNDED` |
| `icsi_specimens/07_egm_notice_annexIII` | `azure:llama-3-3-70b` | `net_worth_rupees` | `FACT_NOT_GROUNDED` |
| `icsi_specimens/07_egm_notice_annexIII` | `azure:llama-3-3-70b` | `paid_up_capital_rupees` | `FACT_NOT_GROUNDED` |
| `icsi_specimens/07_egm_notice_annexIII` | `azure:llama-3-3-70b` | `turnover_rupees` | `FACT_NOT_GROUNDED` |

(134 in total; the rest are in the JSON under `gate_refusals`.)

---

Machine-readable: `reports/prelabel_2026-09-23.json`. Produced by `eval/prelabel/run_prelabel.py --live`. **Agreement between two models is NOT evidence that either is correct. Both can be wrong in the same way, and in this repository they already have been — Indian digit grouping has produced the same 10x misreading more than once. Nothing here is an accuracy measurement. Expert review by a practising Company Secretary (research/TASKS.md H-001) is still required.**
