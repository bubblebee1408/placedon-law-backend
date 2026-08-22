# Reviewer brief — 30 queued items

Assembled evidence only. **Every decision column is blank and stays blank until you fill it.** Nothing here recommends an outcome.

- Source: `corpus/sources/companies_meetings_board_powers_rules_2014.pdf` (22 pages)
- Parsed: 15 rules, instrument status `UNREVIEWED`, `production_usable: False`
- Queue: 30 items, 30 open

## How to record a decision

```bash
python3 scripts/review.py --next        # shows extraction beside the gazette
```

`ADMITTED` · `LIMITED` (needs restriction codes + note) · `SUSPENDED` · `REJECTED`

A `LIMITED` or `REJECTED` decision requires a written reason — the tool enforces it.

## INSTRUMENT — 1 item(s)

### `ri-board_rules_2014-001` — RULE:COMPANIES_MEETINGS_BOARD_POWERS_2014

*HIGH priority* · Gazette G.S.R. 240(E) 31-03-2014; confirm principal, not amendment

| fact | value |
|---|---|
| admission state | HUMAN_REVIEW_PENDING |
| servable now | False |
| artifact | `corpus/sources/companies_meetings_board_powers_rules_2014.pdf` |
| sha256 | `b8b2e01b3d151ee038215c81d4fb10d8…` |
| pages | 22 |
| rules parsed | 15 (r.1–r.15) |
| gazette, per the document | G.S.R. 240 (E) dated 31st March, 2014 |
| made under, per the preamble | 173, 175, 177, 178, 179, 184, 185, 186, 187, 188, 189, 191, 469 |
| principal or amendment? | classified VERIFIED_PRINCIPAL by scripts/acquire_rules.py — 'Short title and commencement' present, no amending language |

**Questions**

1. Is the Gazette number and date correct?
2. Is this the principal instrument, not an amendment or consolidation?
3. Is the commencement date correct?

**Decision:** ______   **Reason:** ______

## RULE — 15 item(s)

### `ri-board_rules_2014-002` — RULE:COMPANIES_MEETINGS_BOARD_POWERS_2014:R1

*HIGH priority* · 6 word(s) still split by extraction -- read text_raw against pages 13-13

| fact | value |
|---|---|
| admission state | HUMAN_REVIEW_PENDING |
| servable now | False |
| heading | Short title and commencement |
| pages | 13–13 of 22 |
| body length | 155 chars |
| sub-rules detected | 1, 2 |
| sections it names | none |
| extraction split words | 6 |
| parser warnings | 6 word(s) still split by extraction -- read text_raw against pages 13-13 |

**Questions**

1. Is the numbered rule boundary correct?
2. Is the heading materially faithful to the gazette?
3. Are the page bounds correct?
4. Is the extracted text usable for legal reasoning?

**Decision:** ______   **Reason:** ______

### `ri-board_rules_2014-003` — RULE:COMPANIES_MEETINGS_BOARD_POWERS_2014:R2

*HIGH priority* · 33 word(s) still split by extraction -- read text_raw against pages 13-13

| fact | value |
|---|---|
| admission state | HUMAN_REVIEW_PENDING |
| servable now | False |
| heading | Definitions |
| pages | 13–13 of 22 |
| body length | 687 chars |
| sub-rules detected | 1, 2 |
| sections it names | none |
| extraction split words | 35  ← read text_raw closely |
| parser warnings | 33 word(s) still split by extraction -- read text_raw against pages 13-13 |

**Questions**

1. Is the numbered rule boundary correct?
2. Is the heading materially faithful to the gazette?
3. Are the page bounds correct?
4. Is the extracted text usable for legal reasoning?

**Decision:** ______   **Reason:** ______

### `ri-board_rules_2014-004` — RULE:COMPANIES_MEETINGS_BOARD_POWERS_2014:R3

*HIGH priority* · 321 word(s) still split by extraction -- read text_raw against pages 13-15

| fact | value |
|---|---|
| admission state | HUMAN_REVIEW_PENDING |
| servable now | False |
| heading | Meetings of Board through video conferencing or other audio visual means |
| pages | 13–15 of 22 |
| body length | 7,301 chars |
| sub-rules detected | 1, 2, 3, 4, 5, 6 |
| sections it names | 118, 173 |
| extraction split words | 336  ← read text_raw closely |
| parser warnings | 321 word(s) still split by extraction -- read text_raw against pages 13-15 |

**Questions**

1. Is the numbered rule boundary correct?
2. Is the heading materially faithful to the gazette?
3. Are the page bounds correct?
4. Is the extracted text usable for legal reasoning?

**Decision:** ______   **Reason:** ______

### `ri-board_rules_2014-005` — RULE:COMPANIES_MEETINGS_BOARD_POWERS_2014:R4

*HIGH priority* · 12 word(s) still split by extraction -- read text_raw against pages 15-15

| fact | value |
|---|---|
| admission state | HUMAN_REVIEW_PENDING |
| servable now | False |
| heading | Matters not to be dealt with in a meeting through video conferencing or other audio visual means |
| pages | 15–15 of 22 |
| body length | 432 chars |
| sub-rules detected | 1 |
| sections it names | none |
| extraction split words | 13 |
| parser warnings | 12 word(s) still split by extraction -- read text_raw against pages 15-15 |

**Questions**

1. Is the numbered rule boundary correct?
2. Is the heading materially faithful to the gazette?
3. Are the page bounds correct?
4. Is the extracted text usable for legal reasoning?

**Decision:** ______   **Reason:** ______

### `ri-board_rules_2014-006` — RULE:COMPANIES_MEETINGS_BOARD_POWERS_2014:R5

*HIGH priority* · 7 word(s) still split by extraction -- read text_raw against pages 15-15

| fact | value |
|---|---|
| admission state | HUMAN_REVIEW_PENDING |
| servable now | False |
| heading | Passing of resolution by circulation |
| pages | 15–15 of 22 |
| body length | 179 chars |
| sub-rules detected | none |
| sections it names | none |
| extraction split words | 9 |
| parser warnings | 7 word(s) still split by extraction -- read text_raw against pages 15-15 |

**Questions**

1. Is the numbered rule boundary correct?
2. Is the heading materially faithful to the gazette?
3. Are the page bounds correct?
4. Is the extracted text usable for legal reasoning?

**Decision:** ______   **Reason:** ______

### `ri-board_rules_2014-007` — RULE:COMPANIES_MEETINGS_BOARD_POWERS_2014:R6

*HIGH priority* · 33 word(s) still split by extraction -- read text_raw against pages 15-15

| fact | value |
|---|---|
| admission state | HUMAN_REVIEW_PENDING |
| servable now | False |
| heading | Committees of the Board |
| pages | 15–15 of 22 |
| body length | 747 chars |
| sub-rules detected | none |
| sections it names | none |
| extraction split words | 34  ← read text_raw closely |
| parser warnings | 33 word(s) still split by extraction -- read text_raw against pages 15-15 |

**Questions**

1. Is the numbered rule boundary correct?
2. Is the heading materially faithful to the gazette?
3. Are the page bounds correct?
4. Is the extracted text usable for legal reasoning?

**Decision:** ______   **Reason:** ______

### `ri-board_rules_2014-008` — RULE:COMPANIES_MEETINGS_BOARD_POWERS_2014:R7

*HIGH priority* · 66 word(s) still split by extraction -- read text_raw against pages 15-16

| fact | value |
|---|---|
| admission state | HUMAN_REVIEW_PENDING |
| servable now | False |
| heading | Establishment of vigil mechanism |
| pages | 15–16 of 22 |
| body length | 1,568 chars |
| sub-rules detected | 1, 2, 3, 4, 5 |
| sections it names | none |
| extraction split words | 71  ← read text_raw closely |
| parser warnings | 66 word(s) still split by extraction -- read text_raw against pages 15-16 |

**Questions**

1. Is the numbered rule boundary correct?
2. Is the heading materially faithful to the gazette?
3. Are the page bounds correct?
4. Is the extracted text usable for legal reasoning?

**Decision:** ______   **Reason:** ______

### `ri-board_rules_2014-009` — RULE:COMPANIES_MEETINGS_BOARD_POWERS_2014:R8

*HIGH priority* · 39 word(s) still split by extraction -- read text_raw against pages 16-16

| fact | value |
|---|---|
| admission state | HUMAN_REVIEW_PENDING |
| servable now | False |
| heading | Powers of Board |
| pages | 16–16 of 22 |
| body length | 988 chars |
| sub-rules detected | 1, 2, 3, 4, 5, 6, 7, 8, 9 |
| sections it names | 179 |
| extraction split words | 40  ← read text_raw closely |
| parser warnings | 39 word(s) still split by extraction -- read text_raw against pages 16-16 |

**Questions**

1. Is the numbered rule boundary correct?
2. Is the heading materially faithful to the gazette?
3. Are the page bounds correct?
4. Is the extracted text usable for legal reasoning?

**Decision:** ______   **Reason:** ______

### `ri-board_rules_2014-010` — RULE:COMPANIES_MEETINGS_BOARD_POWERS_2014:R9

*HIGH priority* · 39 word(s) still split by extraction -- read text_raw against pages 16-16

| fact | value |
|---|---|
| admission state | HUMAN_REVIEW_PENDING |
| servable now | False |
| heading | Disclosures by a director of his interest |
| pages | 16–16 of 22 |
| body length | 699 chars |
| sub-rules detected | 1, 2, 3 |
| sections it names | none |
| extraction split words | 39  ← read text_raw closely |
| parser warnings | 39 word(s) still split by extraction -- read text_raw against pages 16-16 |

**Questions**

1. Is the numbered rule boundary correct?
2. Is the heading materially faithful to the gazette?
3. Are the page bounds correct?
4. Is the extracted text usable for legal reasoning?

**Decision:** ______   **Reason:** ______

### `ri-board_rules_2014-011` — RULE:COMPANIES_MEETINGS_BOARD_POWERS_2014:R10

*HIGH priority* · 22 word(s) still split by extraction -- read text_raw against pages 16-16

| fact | value |
|---|---|
| admission state | HUMAN_REVIEW_PENDING |
| servable now | False |
| heading | Loans to Director etc. under section 185 |
| pages | 16–16 of 22 |
| body length | 614 chars |
| sub-rules detected | 1, 2 |
| sections it names | 185 |
| extraction split words | 25  ← read text_raw closely |
| parser warnings | 22 word(s) still split by extraction -- read text_raw against pages 16-16 |

**Questions**

1. Is the numbered rule boundary correct?
2. Is the heading materially faithful to the gazette?
3. Are the page bounds correct?
4. Is the extracted text usable for legal reasoning?

**Decision:** ______   **Reason:** ______

### `ri-board_rules_2014-012` — RULE:COMPANIES_MEETINGS_BOARD_POWERS_2014:R11

*HIGH priority* · 66 word(s) still split by extraction -- read text_raw against pages 16-16

| fact | value |
|---|---|
| admission state | HUMAN_REVIEW_PENDING |
| servable now | False |
| heading | Loan and investment by a company under section 186 of the Act |
| pages | 16–16 of 22 |
| body length | 1,484 chars |
| sub-rules detected | 1, 2, 3 |
| sections it names | 12, 186 |
| extraction split words | 69  ← read text_raw closely |
| parser warnings | 66 word(s) still split by extraction -- read text_raw against pages 16-16 |

**Questions**

1. Is the numbered rule boundary correct?
2. Is the heading materially faithful to the gazette?
3. Are the page bounds correct?
4. Is the extracted text usable for legal reasoning?

**Decision:** ______   **Reason:** ______

### `ri-board_rules_2014-013` — RULE:COMPANIES_MEETINGS_BOARD_POWERS_2014:R12

*HIGH priority* · 70 word(s) still split by extraction -- read text_raw against pages 16-17

| fact | value |
|---|---|
| admission state | HUMAN_REVIEW_PENDING |
| servable now | False |
| heading | Register |
| pages | 16–17 of 22 |
| body length | 1,397 chars |
| sub-rules detected | 1, 2, 3, 4, 5, 6, 9 |
| sections it names | 186 |
| extraction split words | 71  ← read text_raw closely |
| parser warnings | 70 word(s) still split by extraction -- read text_raw against pages 16-17 |

**Questions**

1. Is the numbered rule boundary correct?
2. Is the heading materially faithful to the gazette?
3. Are the page bounds correct?
4. Is the extracted text usable for legal reasoning?

**Decision:** ______   **Reason:** ______

### `ri-board_rules_2014-014` — RULE:COMPANIES_MEETINGS_BOARD_POWERS_2014:R13

*HIGH priority* · 60 word(s) still split by extraction -- read text_raw against pages 17-17

| fact | value |
|---|---|
| admission state | HUMAN_REVIEW_PENDING |
| servable now | False |
| heading | Special Resolution |
| pages | 17–17 of 22 |
| body length | 1,243 chars |
| sub-rules detected | 1, 2, 3, 4 |
| sections it names | 186 |
| extraction split words | 63  ← read text_raw closely |
| parser warnings | 60 word(s) still split by extraction -- read text_raw against pages 17-17 |

**Questions**

1. Is the numbered rule boundary correct?
2. Is the heading materially faithful to the gazette?
3. Are the page bounds correct?
4. Is the extracted text usable for legal reasoning?

**Decision:** ______   **Reason:** ______

### `ri-board_rules_2014-015` — RULE:COMPANIES_MEETINGS_BOARD_POWERS_2014:R14

*HIGH priority* · 51 word(s) still split by extraction -- read text_raw against pages 17-17

| fact | value |
|---|---|
| admission state | HUMAN_REVIEW_PENDING |
| servable now | False |
| heading | Investments of company to be held in its own na me |
| pages | 17–17 of 22 |
| body length | 1,055 chars |
| sub-rules detected | 1, 2, 3, 4 |
| sections it names | none |
| extraction split words | 51  ← read text_raw closely |
| parser warnings | 51 word(s) still split by extraction -- read text_raw against pages 17-17 |

**Questions**

1. Is the numbered rule boundary correct?
2. Is the heading materially faithful to the gazette?
3. Are the page bounds correct?
4. Is the extracted text usable for legal reasoning?

**Decision:** ______   **Reason:** ______

### `ri-board_rules_2014-016` — RULE:COMPANIES_MEETINGS_BOARD_POWERS_2014:R15

*HIGH priority* · body runs to end-of-document and contains Annexure/Form matter -- the operative text ends earlier; a reviewer must set the boundary; 557 word(s) still split by 

| fact | value |
|---|---|
| admission state | HUMAN_REVIEW_PENDING |
| servable now | False |
| heading | Contract or arrangement with a related party |
| pages | 17–22 of 22 |
| body length | 13,401 chars |
| sub-rules detected | 1, 2, 3 |
| sections it names | 101, 184, 188, 191, 202, 247 |
| extraction split words | 578  ← read text_raw closely |
| parser warnings | body runs to end-of-document and contains Annexure/Form matter -- the operative text ends earlier; a reviewer must set the boundary; 557 word(s) still split by extraction -- read text_raw against pages 17-22 |

**Questions**

1. Is the numbered rule boundary correct?
2. Is the heading materially faithful to the gazette?
3. Are the page bounds correct?
4. Is the extracted text usable for legal reasoning?

**Decision:** ______   **Reason:** ______

## FORM — 1 item(s)

### `ri-board_rules_2014-017` — RULE:COMPANIES_MEETINGS_BOARD_POWERS_2014:R15

*HIGH priority* · body runs to end-of-document and absorbs the Annexure/forms; the operative text ends earlier

| fact | value |
|---|---|
| admission state | HUMAN_REVIEW_PENDING |
| servable now | False |
| heading | Contract or arrangement with a related party |
| pages | 17–22 of 22 |
| body length | 13,401 chars |
| sub-rules detected | 1, 2, 3 |
| sections it names | 101, 184, 188, 191, 202, 247 |
| extraction split words | 578  ← read text_raw closely |
| parser warnings | body runs to end-of-document and contains Annexure/Form matter -- the operative text ends earlier; a reviewer must set the boundary; 557 word(s) still split by extraction -- read text_raw against pages 17-22 |

**Questions**

1. Where does the operative rule text end and the Annexure begin?
2. Should the form tail be excluded from automatic serving?

**Decision:** ______   **Reason:** ______

## LINK — 13 item(s)

Each asserts the Rules are MADE_UNDER an Act section, quoted from the preamble. Check the section exists and its subject matter matches.

| item | Act section | decision |
|---|---|---|
| `ri-board_rules_2014-018` | 173 | |
| `ri-board_rules_2014-019` | 175 | |
| `ri-board_rules_2014-020` | 177 | |
| `ri-board_rules_2014-021` | 178 | |
| `ri-board_rules_2014-022` | 179 | |
| `ri-board_rules_2014-023` | 184 | |
| `ri-board_rules_2014-024` | 185 | |
| `ri-board_rules_2014-025` | 186 | |
| `ri-board_rules_2014-026` | 187 | |
| `ri-board_rules_2014-027` | 188 | |
| `ri-board_rules_2014-028` | 189 | |
| `ri-board_rules_2014-029` | 191 | |
| `ri-board_rules_2014-030` | 469 | |

